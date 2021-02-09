import math
import PIL
import rasterio
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from multiprocessing import Pool, Process
from affine import Affine
from rasterio.warp import reproject, Resampling, calculate_default_transform
from base64 import b64encode
from io import BytesIO
from geojson import MultiLineString


def process_frame(method, *args, **kwargs):
    if method == 'raster':
        return process_frame_raster(*args, **kwargs)
    elif method == 'geojson':
        return process_frame_geojson(*args, **kwargs)
    elif method == 'quiver':
        return process_frame_quiver(*args, **kwargs)
    

def process_frame_raster(data, bounds, src_transform, cmap='viridis'):
    """
    Transform data to Mercator projection and return a base64 encoded image.
    
    Arguments:
    data (3d matrix time:y:x): Raster data to be processed
    bounds ([float: left, float: bottom, float: right, float: top]): 
            Data boundaries in longitude or latitude for left and right or 
            bottom or top respectively
    stepsize ([float: x, float: y]): stepsize between data points in long/lat.
    """

    with rasterio.Env():
        rows, cols = data.shape
        src_crs = {'init': 'EPSG:4326'}
        dst_crs = {'init': 'EPSG:3857'}
  
        dst_transform, width, height = calculate_default_transform(
            src_crs, dst_crs, cols, rows, *bounds)
        
        dst_shape = height, width
        dst = np.zeros(dst_shape)
        
        reproject(
            data,
            dst,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest)
    
    data_norm = dst - np.nanmin(dst)
    data_norm = data_norm / np.nanmax(data_norm)
    data_norm = np.where(np.isfinite(dst), data_norm, 0)
    im = PIL.Image.fromarray(np.uint8(plt.cm.get_cmap(cmap)(data_norm)*255))
        
    f = BytesIO()
    im.save(f, 'png')
    data = b64encode(f.getvalue())
    data = data.decode('ascii')
    imgurl = 'data:image/png;base64,' + data

    return imgurl


def process_frame_quiver(u, v, bounds, src_transform, autoscale=True, color=True,
                         scale_value=None, cmap='viridis'):
    """
    Transform vector field data to Mercator projection, display as vector
    plot and return a base64 encoded image.
    
    Arguments:
    u ([time:y:x]): Eastward direction component of vector.
    v ([time:y:x]): Northward direction component of vector.
    bounds ([float: left, float: bottom, float: right, float: top]): 
        Data boundaries in longitude or latitude for left and right or 
        bottom or top respectively
    stepsize ([float: x, float: y]): stepsize between data points in long/lat.
    autoscale (boolean) (default: True): If True, scale arrows according to magnitude. If 
        False, All arrows have the same size.
    color (boolean) (default: True): If True, color arrows according to magnitude. If 
        False, All arrows have the same color.
    """
    #matplotlib.use('Agg')

    with rasterio.Env():
        rows, cols = u.shape
        src_crs = {'init': 'EPSG:4326'}
        dst_crs = {'init': 'EPSG:3857'}

        dst_transform, width, height = rasterio.warp.calculate_default_transform(
            src_crs, dst_crs, cols, rows, *bounds)
        
        dst_shape = height, width
        dst_u, dst_v = np.zeros(dst_shape), np.zeros(dst_shape)
        
        reproject(
            u,
            dst_u,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest)

        reproject(
            v,
            dst_v,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest)

    fig, ax = plt.subplots()
    
    if not autoscale:
        dst_u = dst_u / np.sqrt(dst_u**2 + dst_v**2)
        dst_v = dst_v / np.sqrt(dst_u**2 + dst_v**2)

        if color:
            ax.quiver(dst_u[::-1,:], dst_v[::-1,:], (dst_u * dst_v), pivot='middle', scale=scale_value)
        else:
            ax.quiver(dst_u[::-1,:], dst_v[::-1,:], pivot='middle', scale=scale_value)
    else:
        if color:
            ax.quiver(dst_u[::-1,:], dst_v[::-1,:], (dst_u * dst_v), pivot='middle', scale=scale_value)
        else:
            ax.quiver(dst_u[::-1,:], dst_v[::-1,:], pivot='middle', scale=scale_value)

    ax.axis('off')
    fig.gca().set_aspect('equal', adjustable='box')
    ax.set_xlim(left=-0.25, right=dst_u.shape[1])
    ax.set_ylim(bottom=-0.25, top=dst_u.shape[0])

    f = BytesIO()
    fig.savefig(f, format='png', dpi=600, transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close()
    data = b64encode(f.getvalue())
    data = data.decode('ascii')
    imgurl = 'data:image/png;base64,' + data

    return imgurl


def process_frame_geojson(u, v, long, lat, autoscale=True, scale=0.5):
    """
    Generates arrows in a GeoJSON format from vector field data.
    
    Arguments:
    u ([time:y:x]): Eastward direction component of vector.
    v ([time:y:x]): Northward direction component of vector.
    long ([int]): Array of longitude values.
    long ([int]): Array of latitude values.
    autoscale (boolean) (default: True): If True, scale arrows according to magnitude. If 
        False, All arrows have the same size.
    scale (float) (default: 0.5): Arrow scale in coordinates relative to arrow
        magnitude if not autoscaled.
    """
    arrows = []
    length = 0
    
    for i in range(len(lat)):
        for j in range(len(long)):
            arrows.append(calc_arrow(u[i][j], v[i][j], long[j], lat[i], autoscale, scale))
    
    return MultiLineString(arrows)


def calc_arrow(u, v, long, lat, autoscale, scale):
    """
    Calculates coordinates specifying an arrow.
    
    Arguments:
    u (float): Eastward direction component of vector.
    v (float): Northward direction component of vector.
    long (int): Longitude value.
    long (int): Latitude value.
    autoscale (boolean) (default: True): If True, scale arrow according to magnitude.
    scale (float) (default: 0.5): Arrow scale in coordinates relative to arrow
        magnitude if not autoscaled.
    """
    angle = np.arctan2(v, u)

    if autoscale:
        length = np.sqrt(np.abs(u * v)) * scale
    else:
        length = scale
    
    head_scale = 0.1
    head_angle = 50
    head_angle_l = np.radians(270) - np.radians(head_angle)
    head_angle_r = np.radians(270) + np.radians(head_angle)
    
    dx = (length/2) * np.cos(angle)
    dy = (length/2) * np.sin(angle)
    
    begin = [long - dx, lat - dy]
    end = [long + dx, lat + dy]
    
    dx_head_l = (length*head_scale) * np.cos(angle+head_angle_l)
    dy_head_l = (length*head_scale) * np.sin(angle+head_angle_l)
    
    dx_head_r = (length*head_scale) * np.cos(angle+head_angle_r)
    dy_head_r = (length*head_scale) * np.sin(angle+head_angle_r)
    
    head_l = [end[0] + dx_head_l, end[1] + dy_head_l]
    head_r = [end[0] - dx_head_r, end[1] - dy_head_r]
    
    return [begin, end, head_l, end, head_r]
