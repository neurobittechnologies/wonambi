"""Convenient module to convert data based on simple mathematical operations.
"""
from inspect import getfullargspec
from logging import getLogger

# for Math
from numpy import (absolute,
                   angle,
                   asarray,
                   diff,
                   empty,
                   exp,
                   gradient,
                   isinf,
                   log,
                   log10,
                   median,
                   mean,
                   nan,
                   nanmean,
                   nanstd,
                   ones,
                   pad,
                   sign,
                   sqrt,
                   square,
                   sum,
                   std,
                   where,
                   unwrap)
from scipy.signal import detrend, hilbert, fftconvolve
from scipy.stats import mode

lg = getLogger(__name__)

NOKEEPDIM = (median, mode)


def math(data, operator=None, operator_name=None, axis=None):
    """Apply mathematical operation to each trial and channel individually.

    Parameters
    ----------
    data : instance of DataTime, DataFreq, or DataTimeFreq

    operator : function or tuple of functions, optional
        function(s) to run on the data.
    operator_name : str or tuple of str, optional
        name of the function(s) to run on the data.
    axis : str, optional
        for functions that accept it, which axis you should run it on.

    Returns
    -------
    instance of Data
        data where the trials underwent operator.

    Raises
    ------
    TypeError
        If you pass both operator and operator_name.
    ValueError
        When you try to operate on an axis that has already been removed.

    Notes
    -----
    operator and operator_name are mutually exclusive. operator_name is given
    as shortcut for most common operations.

    If a function accepts an 'axis' argument, you need to pass 'axis' to the
    constructor. In this way, it'll apply the function to the correct
    dimension.

    The possible point-wise operator_name are:
    'absolute', 'angle', 'dB' (=10 * log10), 'exp', 'log', 'sqrt', 'square',
    'unwrap'

    The operator_name's that need an axis, but do not remove it:
    'hilbert', 'diff', 'detrend'

    The operator_name's that need an axis and remove it:
    'mean', 'median', 'mode', 'std'

    Examples
    --------
    You can pass a single value or a tuple. The order starts from left to
    right, so abs of the hilbert transform, should be:

    >>> rms = math(data, operator_name=('hilbert', 'abs'), axis='time')

    If you want to pass the power of three, use lambda (or partial):

    >>> p3 = lambda x: power(x, 3)
    >>> data_p3 = math(data, operator=p3)

    Note that lambdas are fine with point-wise operation, but if you want them
    to operate on axis, you need to pass ''axis'' as well, so that:

    >>> std_ddof = lambda x, axis: std(x, axis, ddof=1)
    >>> data_std = math(data, operator=std_ddof)

    If you don't pass 'axis' in lambda, it'll never know on which axis the
    function should be applied and you'll get unpredictable results.

    If you want to pass a function that operates on an axis and removes it (for
    example, if you want the max value over time), you need to add an argument
    in your function called ''keepdims'' (the values won't be used):

    >>> def func(x, axis, keepdims=None):
    >>>     return nanmax(x, axis=axis)
    """
    if operator is not None and operator_name is not None:
        raise TypeError('Parameters "operator" and "operator_name" are '
                        'mutually exclusive')

    # turn input into a tuple of functions in operators
    if operator_name is not None:
        if isinstance(operator_name, str):
            operator_name = (operator_name, )

        operators = []
        for one_operator_name in operator_name:
            operators.append(eval(one_operator_name))
        operator = tuple(operators)

    # make it an iterable
    if callable(operator):
        operator = (operator, )

    operations = []
    for one_operator in operator:
        on_axis = False
        keepdims = True

        try:
            args = getfullargspec(one_operator).args
        except TypeError:
            lg.debug('func ' + str(one_operator) + ' is not a Python '
                     'function')
        else:
            if 'axis' in args:
                on_axis = True

                if axis is None:
                    raise TypeError('You need to specify an axis if you '
                                    'use ' + one_operator.__name__ +
                                    ' (which applies to an axis)')

            if 'keepdims' in args or one_operator in NOKEEPDIM:
                keepdims = False

        operations.append({'name': one_operator.__name__,
                           'func': one_operator,
                           'on_axis': on_axis,
                           'keepdims': keepdims,
                           })

    output = data._copy()

    if axis is not None:
        idx_axis = data.index_of(axis)

    first_op = True
    for op in operations:
        #lg.info('running operator: ' + op['name'])
        func = op['func']

        if func == mode:
            func = lambda x, axis: mode(x, axis=axis)[0]

        for i in range(output.number_of('trial')):

            # don't copy original data, but use data if it's the first operation
            if first_op:
                x = data(trial=i)
            else:
                x = output(trial=i)

            if op['on_axis']:
                lg.debug('running ' + op['name'] + ' on ' + str(idx_axis))

                try:
                    if func == diff:
                        lg.debug('Diff has one-point of zero padding')
                        x = _pad_one_axis_one_value(x, idx_axis)
                    output.data[i] = func(x, axis=idx_axis)

                except IndexError:
                    raise ValueError('The axis ' + axis + ' does not '
                                     'exist in [' +
                                     ', '.join(list(data.axis.keys())) + ']')

            else:
                lg.debug('running ' + op['name'] + ' on each datapoint')
                output.data[i] = func(x)

        first_op = False

        if op['on_axis'] and not op['keepdims']:
            del output.axis[axis]

    return output


def get_descriptives(data):
    """Get mean, SD, and mean and SD of log values.
    
    Parameters
    ----------
    data : ndarray
        Data with segment as first dimension
        and all other dimensions raveled into second dimension.
        
    Returns
    -------
    dict of ndarray
        each entry is a 1-D vector of descriptives over segment dimension        
    """
    output = {}
    dat_log = log(abs(data))
    output['mean'] = nanmean(data, axis=0)
    output['sd'] = nanstd(data, axis=0)
    output['mean_log'] = nanmean(dat_log, axis=0)
    output['sd_log'] = nanstd(dat_log, axis=0)
    
    return output


def slopes(data, s_freq, level='all', smooth=0.05):
    """Get the slopes (average and/or maximum) for each quadrant of a slow
    wave, as well as the combination of quadrants 2 and 3.
    
    Parameters
    ----------
    data : ndarray
        raw data as vector
    s_freq : int
        sampling frequency
    level : str
        if 'average', returns average slopes (uV / s). if 'maximum', returns 
        the maximum of the slope derivative (uV / s**2). if 'all', returns all.
    smooth : float or None
        if not None, signal will be smoothed by moving average, with a window 
        of this duration
        
    Returns
    -------
    tuple of ndarray
        each array is len 5, with q1, q2, q3, q4 and q23. First array is 
        average slopes and second is maximum slopes.
        
    Notes
    -----
    This function is made to take automatically detected start and end 
    times AS WELL AS manually delimited ones. In the latter case, the first
    and last zero has to be detected within this function.
    """
    nan_array = empty((5,))
    nan_array[:] = nan
    idx_trough = data.argmin()
    idx_peak = data.argmax()    
    if idx_trough >= idx_peak:
        return nan_array, nan_array
    
    zero_crossings_0 = where(diff(sign(data[:idx_trough])))[0]
    zero_crossings_1 = where(diff(sign(data[idx_trough:idx_peak])))[0]
    zero_crossings_2 = where(diff(sign(data[idx_peak:])))[0]
    if zero_crossings_1.any():
        idx_zero_1 = idx_trough + zero_crossings_1[0]
    else:
        return nan_array, nan_array
    
    if zero_crossings_0.any():
        idx_zero_0 = zero_crossings_0[-1]
    else:
        idx_zero_0 = 0
        
    if zero_crossings_2.any():
        idx_zero_2 = idx_peak + zero_crossings_2[0]
    else:
        idx_zero_2 = len(data) - 1
        
    avgsl = nan_array
    if level in ['average', 'all']:
        q1 = data[idx_trough] / ((idx_trough - idx_zero_0) / s_freq)
        q2 = data[idx_trough] / ((idx_zero_1 - idx_trough) / s_freq)
        q3 = data[idx_peak] / ((idx_peak - idx_zero_1) / s_freq)
        q4 = data[idx_peak] / ((idx_zero_2 - idx_peak) / s_freq)
        q23 = (data[idx_peak] - data[idx_trough]) \
                / ((idx_peak - idx_trough) / s_freq)
        avgsl = asarray([q1, q2, q3, q4, q23])
        avgsl[isinf(avgsl)] = nan
    
    maxsl = nan_array
    if level in ['maximum', 'all']:
        
        if smooth is not None:
            win = int(smooth * s_freq)
            flat = ones(win)
            data = fftconvolve(data, flat / sum(flat), mode='same')
                
        if idx_trough - idx_zero_0 >= win:
            maxsl[0] = min(gradient(data[idx_zero_0:idx_trough]))
            
        if idx_zero_1 - idx_trough >= win:
            maxsl[1] = max(gradient(data[idx_trough:idx_zero_1]))
            
        if idx_peak - idx_zero_1 >= win:
            maxsl[2] = max(gradient(data[idx_zero_1:idx_peak]))
            
        if idx_zero_2 - idx_peak >= win:
            maxsl[3] = min(gradient(data[idx_peak:idx_zero_2]))
            
        if idx_peak - idx_trough >= win:
            maxsl[4] = max(gradient(data[idx_trough:idx_peak]))
            
        maxsl[isinf(maxsl)] = nan
        
    return avgsl, maxsl


def _pad_one_axis_one_value(x, idx_axis):
    pad_width = [(0, 0)] * x.ndim
    pad_width[idx_axis] = (1, 0)
    return pad(x, pad_width=pad_width, mode='mean')


# additional operators
def dB(x):
    return 10 * log10(x)
