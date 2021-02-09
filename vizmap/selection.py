import matplotlib.path as mplPath
import numpy as np
from math import sin, cos, radians, sqrt, atan2, asin


def find_selection_polygon(coords, lat, long):
    """
    Finds the coordinates in lat and long enclosed by the polygon defined by
    the coordinates in coords. Returns a mask array that masks points not in
    the selection
    
    Arguments:
    coords ([[int: long, int: lat]]): Array of coordinates of selection polygon.
    lat ([int]): Array of latitude coordinates the selection should be found in.
    long ([int]): Array of longitude coordinates the selection should be found in.
    """
    poly = mplPath.Path(coords)
    xmin, xmax, ymin, ymax = get_poly_bounds(coords)
    x_lo = np.searchsorted(long, xmin) - 1
    x_hi = np.searchsorted(long, xmax) + 1
    y_lo = len(lat) - np.searchsorted(np.flip(lat), ymax) - 1
    y_hi = len(lat) - np.searchsorted(np.flip(lat), ymin) + 1
    
    mask = np.full((len(lat), len(long)), True)
    
    for y in range(y_lo, y_hi):
        for x in range(x_lo, x_hi):
            if poly.contains_point([long[x], lat[y]]):
                mask[y,x] = False

    return mask


def find_selection_rectangle(coords, lat, long):
    """
    Finds the coordinates in lat and long enclosed by the rectangle
    defined by the coordinates in coords. Returns a mask array that masks
    points not in the selection.
    
    Arguments:
    coords ([[int: long, int: lat]]): Coordinates of selection rectangle.
    lat ([int]): Array of latitude coordinates the selection should be found in.
    long ([int]): Array of longitude coordinates the selection should be found in.
    """
    xmin, xmax, ymin, ymax = get_poly_bounds(coords)
    x_lo = np.searchsorted(long, xmin) - 1
    x_hi = np.searchsorted(long, xmax) + 1
    y_lo = len(lat) - np.searchsorted(np.flip(lat), ymax) - 1
    y_hi = len(lat) - np.searchsorted(np.flip(lat), ymin) + 1
    
    mask = np.full((len(lat), len(long)), True)
    
    mask[y_lo:y_hi,x_lo:x_hi] = False
    
    return mask


def find_selection_circle(center, radius, lat, long):
    """
    Finds the coordinates in lat and long enclosed by the circle
    defined by the central coordinate and radius. Returns a mask array
    that masks points not in the selection.
    
    Arguments:
    center ([int: long, int: lat]): Coordinate specifying the center of the circle.
    radius (float||int): Radius of circle in meters.
    lat ([int]): Array of latitude coordinates the selection should be found in.
    long ([int]): Array of longitude coordinates the selection should be found in.
    """
    ymin, ymax = get_circle_y_bounds(center, radius)
    y_lo = len(lat) - np.searchsorted(np.flip(lat), ymax)
    y_hi = len(lat) - np.searchsorted(np.flip(lat), ymin) -1
    
    mask = np.full((len(lat), len(long)), True)
    
    for y in range(y_lo, y_hi):
        for x in range(len(long)):
            if distance(center, [long[x], lat[y]]) < radius:
                mask[y,x] = False
    
    return mask


def get_circle_y_bounds(center, radius):
    deg = radius / 110    #110 is approximally the maximum amount of km of one degree latitude
    ymin = center[1] - deg
    ymax = center[1] + deg
    return ymin, ymax

                
def get_poly_bounds(poly_points):
    xmin = np.min(poly_points[:,0])
    xmax = np.max(poly_points[:,0])
    ymin = np.min(poly_points[:,1])
    ymax = np.max(poly_points[:,1])
    return xmin, xmax, ymin, ymax
    
        
def is_rectangle(poly_points):
    if len(poly_points) == 5:
        if poly_points[0][0] == poly_points[1][0] and \
                poly_points[0][0] == poly_points[4][0] and \
                poly_points[0][1] == poly_points[3][1] and \
                poly_points[1][1] == poly_points[2][1] and \
                poly_points[2][0] == poly_points[3][0]:
            return True
    return False


def distance(origin, destination):
    """
    Distance between two coordinates using Haversine formula
    """
    lon1, lat1 = origin
    lon2, lat2 = destination
    radius = 6371    # earth radius in km

    dlat = radians(lat2-lat1)
    dlon = radians(lon2-lon1)
    
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a), sqrt(1-a))
    d = radius * c

    return d


def find_selection(selection, lat, long):
    """
    Determines selection type and returns the selection
    """
    if selection['geometry']['type'] == 'Point':
        return find_selection_circle(selection['geometry']['coordinates'],
                                     selection['properties']['style']['radius']/1000,
                                     lat, long)
    elif selection['geometry']['type'] == 'Polygon':
        coords = np.array(selection['geometry']['coordinates'][0])
        if is_rectangle(coords):
            return find_selection_rectangle(coords, lat, long)
        else:
            return find_selection_polygon(coords, lat, long)
