from ipyleaflet import *
from ipywidgets import *

from .layer import *
from .selection import *

basemaps = basemaps # ipyleaflet's basemaps

class VizMap:
    #def __init__(self, basemap=basemaps.OpenStreetMap.Mapnik, center=(0,0), zoom=1):
    #    self.map = Map(basemap=basemap, center=center, zoom=zoom)
    def __init__(self, **kwargs):
        self.map = Map(**kwargs)
        self.layers = []
        self.selections = []
        
        # initialize widgets
        play = Play(
            value=0,
            min=0,
            max=100,
            step=1,
            interval=50,
            description="Play",
        )
        
        fps_text = IntText(
            value=20,
            disabled=False,
        )
        fps_text.layout.max_width = '50px'
        
        def fps_update(change):
            play.interval = 1000 / change['new']
        
        fps_text.observe(fps_update, 'value')
        
        play_box = HBox([HTML('FPS'), fps_text, play])
        play_control = WidgetControl(widget=play_box, position='bottomleft')
        self.play_control = play_control

        draw_control = self.get_draw_control()

        def handle_draw(_self, action, geo_json):
            if action == 'created':
                self.selections.append(geo_json)
            else:
                self.selections.remove(geo_json)

        draw_control.on_draw(handle_draw)
        
        layers = LayersControl(position='topleft')
        
        self.map.add_control(play_control)
        self.map.add_control(layers)
        self.map.add_control(draw_control)

        
    def add_raster(self, *args, **kwargs):
        """
        Add a regular raster vizualisation layer.
        
        Arguments:
        See RasterLayer
        """
        layer = RasterLayer(*args, **kwargs, name=str(len(self.layers)))
        
        self.layers.append(layer)
        
        if len(layer.data) > self.play_control.widget.children[2].max:
            self.play_control.widget.children[2].max = len(layer.data)
            
        jslink((self.play_control.widget.children[2], 'value'),
               (layer.frame_control.widget.children[0], 'value'))
        
        self.map.add_layer(layer.layer_obj)
        self.map.add_control(layer.opacity_control)
        self.map.add_control(layer.frame_control)
    
    
    def add_wind(self, *args, **kwargs):
        """
        Add a wind vizualisation layer.
        
        Arguments:
        See WindLayer
        """
        layer = WindLayer(*args, **kwargs, name=str(len(self.layers)))
        
        if len(layer.u) > self.play_control.widget.children[2].max:
            self.play_control.widget.children[2].max = len(layer.u)
            
        jslink((self.play_control.widget.children[2], 'value'),
               (layer.frame_control.widget.children[0], 'value'))
        
        self.layers.append(layer)
        self.map.add_layer(layer.layer_obj)
        self.map.add_control(layer.frame_control)
        
        
    def get_draw_control(self):
        draw_control = DrawControl()

        draw_control.polygon = {
            "shapeOptions": {
                "color": "#fca45d",
                "fillOpacity": 0.0
            }
        }
        
        draw_control.rectangle = {
            "shapeOptions": {
                "color": "#fca45d",
                "fillOpacity": 0.0
            }
        }

        draw_control.circle = {
            "shapeOptions": {
                "color": "#fca45d",
                "fillOpacity": 0.0
            }
        }
        return draw_control
    
    
    def remove_layer(self, layer):
        """
        Arguments:
        layer (int): Index of layer to be removed. Should be their name within
            the layer control widget.
        """
        self.map.remove_layer(self.layers[layer].layer_obj)
        self.map.remove_control(self.layers[layer].frame_control)
        if type(self.layers[layer]) == RasterLayer:
            self.map.remove_control(self.layers[layer].opacity_control)
            
        self.layers.pop(layer)
        
        # Rename layers so their names are their correct index again.
        for i, layer in enumerate(self.layers):
            layer.layer_obj.name = str(i)
        
        
    def clear_map(self):
        for i in reversed(range(len(self.layers))):
            self.remove_layer(i)
            
        
    def get_selection(self, selection, layer=0):
        """
        Get one or multiple selections from a layer.
        
        Arguments:
        selection (int||[int]): Index/indices of selection(s) to be retrieved.
        layer (int): Index of layer from which the selection(s) is/are
            retrieved.
        """
        if hasattr(selection, "__iter__"):
            selections = [self.selections[i] for i in selection]
        else:
            selections = self.selections[selection]
        return (self.layers[layer].get_selection(selections))
        
        
    def display(self):
        display(self.map)
        
    def __str__(self):
        return self.map.__str__()
    
    def _repr_html_(self):
        return display(self.map)
    
