import threading
import numpy as np
import netCDF4 as nc
import gdal
from multiprocessing import Pool, cpu_count
from affine import Affine
from ipyleaflet import *
from ipywidgets import FloatSlider, IntSlider, Play, jslink, Box, Label

from .selection import *
from .processing import *
from .debounce import *


class Layer:
    def read_time(self, time):
        self.time = nc.num2date(time[:], units=time.units,
                                calendar=time.calendar)
        
    def __str__(self):
        return f"{self.layer_obj}, frame={self.frame}"
    
    def __repr__(self):
        return f"Layer({self.layer_obj}, frame={self.frame})"


class RasterLayer(Layer):
    """
    Layer for regular, single-variable raster data.
    """
    def __init__(self, file, data, time='time', lat='latitude',
                 long='longitude', cmap='viridis', frame=0, name=None):
        """
        Arguments:
        file (string): Filename of dataset file to be visualized.
        data (string): Name of data variable to be visualized within dataset file.
        time (string): Name of time dimension within dataset file.
        lat (string): Name of latitude dimension within dataset file.
        long (string): Name of longitude dimension within dataset file.
        cmap (string): Colormap name. Matplotlib colormaps are used.
        frame (int): Frame first displayed.
        name (string): Layer name. Normally the index within the map.
        """
        ds = nc.Dataset(file)
        self.coords = [ds[lat][:], ds[long][:]]
        self.data = ds[data]
        self.read_time(ds[time])
        self.cmap = cmap
        self.cache = [0 for i in range(len(self.data))]
        
        tmp = gdal.Open(f"NETCDF:{file}:{data}")
        t = tmp.GetGeoTransform()
        t = [t[1], t[2], t[0], t[4], t[5], t[3]]
        self.transform = Affine(*t)
        del tmp
        
        self.frame = frame
        self.bounds = calc_bounds(self.coords)
        self.bounds_img = calc_bounds(self.coords, type='edge')
        self.create_layer(name)
        
        
    def create_layer(self, name):
        url = process_frame('raster', self.data[self.frame], self.bounds,
                             self.transform, self.cmap)
        self.cache[self.frame] = url
        self.buffer_frames(self.frame+1, 50)
        
        bounds = [(self.bounds_img[1], self.bounds_img[0]), 
                  (self.bounds_img[3], self.bounds_img[2])]
        
        self.layer_obj = ImageOverlay(url=url, bounds=bounds, opacity=0.5, name=name)
        
        opacity_slider = FloatSlider(description='Opacity:', 
                                     min=0.0, max=1.0, value=0.5, step=0.01)
        opacity_control = WidgetControl(widget=opacity_slider,
                                        position='topright')
        
        jslink((opacity_slider, 'value'), (self.layer_obj, 'opacity'))
        
        frame_slider = IntSlider(
            value=0,
            min=0,
            max=len(self.data)-1,
            step=1,
            description='Time:',
            continuous_update=True,
            orientation='horizontal',
            readout=False,
        )
        label = Label(str(self.time[frame_slider.value]))
        label.layout.padding = '5px'
        box = Box([frame_slider, label])
        
        frame_control = WidgetControl(widget=box, position='bottomright')
        
        def update_frame(change):
            label.value = str(self.time[change.new])
            self.update_frame(change.new)

        frame_slider.observe(update_frame, 'value')
        
        self.frame_control = frame_control
        self.opacity_control = opacity_control
        
        
    def get_selection(self, selection):
        if isinstance(selection, list) or isinstance(selection, tuple) or \
                isinstance(selection, np.ndarray):
            mask = find_selection(selection[0], self.coords[0], self.coords[1])
            for i in range(1, len(selection)):
                mask = mask & find_selection(selection[i], self.coords[0], self.coords[1])
        else:
            mask = find_selection(selection, self.coords[0], self.coords[1])
        return np.ma.array(self.data[self.frame], mask=mask)


    def update_frame(self, i=None):
        if i is None:
            i = self.frame + 1
        self.frame = i
        
        if i % 10 == 0:
            self.buffer_frames(self.frame+1, 40)
            
        if self.cache[i] != 0:
            self.layer_obj.url = self.cache[i]
        else:
            img = process_frame('raster', self.data[i], self.bounds_img,
                                 self.transform, cmap=self.cmap)
            self.layer_obj.url = img
            self.cache[i] = img
            self.buffer_frames(i+1, 50)#, finish=True)
            
    
    @debounce(0.3)    # Delay buffering when scrubbing through frames.
    def buffer_frames(self, start, n, finish=False, processes=cpu_count()):
        with threading.Lock():
            data = self.data[start:start+n]
            
        def cache_frame(result):
            self.cache[result[1]] = result[0]
        
        pool = Pool(processes=processes)
        results = []
        
        for i in range(n):
            if self.cache[start+i] != 0:
                continue
            args = (start+i, 'raster', data[i], self.bounds_img,
                    self.transform, self.cmap)
            r = pool.apply_async(calc_frame, args, callback=cache_frame)
            results.append(r)
            
        if finish:
            for r in results:
                r.wait()
            
    
class WindLayer(Layer):
    """
    Layer for wind data consisting of eastward (u) and northward (v) velocity.
    """
    def __init__(self, file, u='u', v='v', time='time', lat='latitude',
                 long='longitude', stride=1, method='geojson',
                 cmap='viridis', autoscale=True, color=False, scale_value=0.5,
                 frame=0, name=None):
        """
        Arguments:
        file (string): Filename of dataset file to be visualized.
        u (string): Name of data variable to be visualized within dataset file.
        v (string): Name of data variable to be visualized within dataset file.
        time (string): Name of time dimension within dataset file.
        lat (string): Name of latitude dimension within dataset file.
        long (string): Name of longitude dimension within dataset file.
        stride (int): Using a stride of n means reading every nth value from
            the array. Higher stride results in less arrows and higher
            performance.
        method (string): Visualization method. 'quiver' and 'geojson' are
            available.
        cmap (string): Colormap name. Matplotlib colormaps are used.
        autoscale (boolean): If True, arrows are scaled according to magnitude,
            else all arrows have equal length.
        color (boolean): If True, arrows are colored according to magnitude.
            Only available for 'quiver' method.
        scale_value (float||int): Scale value arrows arrows are scaled by,
            meaning depends on method and whether or not autoscaled.
        frame (int): Frame first displayed.
        name (string): Layer name. Normally the index within the map.
        """
        ds = nc.Dataset(file)
        self.coords = [ds[lat], ds[long]]
        self.u = ds[u]
        self.v = ds[v]
        self.stride = stride
        self.read_time(ds[time])
        self.cache = [0 for i in range(len(self.u))]
        
        self.method = method
        self.cmap = cmap
        self.autoscale = autoscale
        self.color = color
        self.scale_value = scale_value
        
        tmp = gdal.Open(f"NETCDF:{file}:{u}")
        t = tmp.GetGeoTransform()
        t = [t[1]*stride, t[2], t[0], t[4], t[5]*stride, t[3]]
        self.transform = Affine(*t)
        del tmp
        
        self.frame = frame
        self.bounds = calc_bounds(self.coords)
        self.bounds_img = calc_bounds(self.coords, type='edge')
        self.coords = [ds[lat][::self.stride], ds[long][::self.stride]]
        self.create_layer(name)
        
        
    def get_frame(self, frame):
        if self.method == 'geojson':
            return process_frame('geojson', self.u[frame][::self.stride, ::self.stride],
                            self.v[frame][::self.stride, ::self.stride],
                            self.coords[1], self.coords[0], self.autoscale,
                            self.scale_value)
        elif self.method == 'quiver':
            return process_frame('quiver', self.u[frame][::self.stride, ::self.stride],
                             self.v[frame][::self.stride, ::self.stride],
                             self.bounds, self.transform, self.autoscale,
                             self.color, self.scale_value, cmap=self.cmap)
        
        
    def create_layer(self, name):
        frame = self.get_frame(self.frame)
        self.cache[self.frame] = frame
        
        bounds = [(self.bounds_img[1], self.bounds_img[0]),
                  (self.bounds_img[3], self.bounds_img[2])]
        
        if self.method == 'geojson':
            self.layer_obj = GeoJSON(data=frame, name=name,style={"color":"#000000",
                                     "weight": 1, "opacity": 0.65})
        elif self.method == 'quiver':
            self.layer_obj = ImageOverlay(url=frame, bounds=bounds, opacity=0.5, name=name)
        
        self.buffer_frames(self.frame+1, 50)
        
        
        frame_slider = IntSlider(
            value=0,
            min=0,
            max=len(self.u)-1,
            step=1,
            description='Time:',
            continuous_update=True,
            orientation='horizontal',
            readout=False,
        )
        label = Label(str(self.time[frame_slider.value]))
        box = Box([frame_slider, label])
        
        frame_control = WidgetControl(widget=box, position='bottomright')
        
        def update_frame(change):
            label.value = str(self.time[change.new])
            self.update_frame(change.new)

        frame_slider.observe(update_frame, 'value')
        
        self.frame_control = frame_control
        
        
    def get_selection(self, selection):
        if isinstance(selection, list) or isinstance(selection, tuple) or \
                isinstance(selection, np.ndarray):
            mask = find_selection(selection[0], self.coords[0], self.coords[1])
            for i in range(1, len(selection)):
                mask = mask & find_selection(selection[i], self.coords[0], self.coords[1])
        else:
            mask = find_selection(selection, self.coords[0], self.coords[1])
        return (np.ma.array(self.u[self.frame], mask=mask),
                np.ma.array(self.u[self.frame], mask=mask))
    

    def update_frame(self, i=None):
        if i is None:
            i = self.frame + 1
        self.frame = i
        
        if i % 10 == 0:
            self.buffer_frames(self.frame+1, 40)
            
        if self.cache[i] != 0:
            if self.method == 'geojson':
                self.layer_obj.data = self.cache[i]
            elif self.method == 'quiver':
                self.layer_obj.url = self.cache[i]
        else:
            frame = self.get_frame(i)
            
            if self.method == 'geojson':
                self.layer_obj.data = frame
            elif self.method == 'quiver':
                self.layer_obj.url = frame
                
            self.cache[i] = frame
            self.buffer_frames(i+1, 50)
        
        
    @debounce(0.3)    # Delay buffering when scrubbing through frames.
    def buffer_frames(self, start, n, finish=False, processes=cpu_count()):
        with threading.Lock():
            u = self.u[start:start+n, ::self.stride, ::self.stride]
            v = self.v[start:start+n, ::self.stride, ::self.stride]
        
        def cache_frame(result):
            self.cache[result[1]] = result[0]
        
        pool = Pool(processes=processes)
        results = []
        
        for i in range(n):
            if self.cache[start+i] != 0:
                continue
                
            if method == 'geojson':
                args = (start+i, 'geojson', u[i], v[i], self.coords[1],
                        self.coords[0], self.autoscale, self.scale_value)
            elif method == 'quiver':
                args = (start+i, 'quiver', u[i], v[i], self.bounds_img,
                        self.transform, self.autoscale, self.color,
                        self.scale_value,  self.cmap)
                
            r = pool.apply_async(calc_frame, args, callback=cache_frame)
            results.append(r)
            
        if finish:
            for r in results:
                r.wait()
                
                
def calc_frame(frame, method, *args, **kwargs):
    if method == 'raster':
        img = process_frame_raster(*args, **kwargs)
    elif method == 'geojson':
        img = process_frame_geojson(*args, **kwargs)
    elif method == 'quiver':
        img = process_frame_quiver(*args, **kwargs)
    return img, frame


def calc_bounds(coords, step=None, type='true'):
    left = min(coords[1])
    bottom = min(coords[0])
    right = max(coords[1])
    top = max(coords[0])

    if step == None:
        step = (np.abs(coords[1][1]-coords[1][0]), np.abs(coords[0][1]-coords[0][0]))

    if type == 'true':
        return (left, bottom, right, top)
    elif type == 'edge':
        return (left-step[0]/2, bottom-step[1]/2, right+step[0]/2, top+step[1]/2)

