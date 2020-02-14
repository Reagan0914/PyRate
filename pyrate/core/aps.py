#   This Python module is part of the PyRate software package.
#
#   Copyright 2020 Geoscience Australia
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""
This Python module implements a spatio-temporal filter method
for correcting interferograms for atmospheric phase screen (APS)
signals.
"""
import os
from collections import OrderedDict
from copy import deepcopy

import numpy as np
from numpy import isnan
from scipy.fftpack import fft2, ifft2, fftshift, ifftshift
from scipy.interpolate import griddata

from core import shared, ifgconstants as ifc, mpiops, config as cf
from core.algorithm import get_epochs
from core.covariance import cvd_from_phase, RDist
from core.logger import pyratelogger as log
from core.shared import Ifg
from core.timeseries import time_series
from merge import _assemble_tiles


def _wrap_spatio_temporal_filter(ifg_paths, params, tiles, preread_ifgs):
    """A wrapper for the spatio-temporal filter so it can be tested. See
    docstring for spatio_temporal_filter.
    
    Args:
        ifg_paths:
    
    Args:
      tiles: param preread_ifgs:
      ifg_paths: param params:

    Args:
      preread_ifgs: 
      ifg_paths: 
      params: 
      tiles: 

    Returns:
      

    """
    if not params[cf.APSEST]:
        log.info("APS correction not required.")
        return

    # perform some checks on existing ifgs
    log.debug("Checking APS correction status")
    if mpiops.run_once(shared.check_correction_status, ifg_paths, ifc.PYRATE_APS_ERROR):
        log.debug("Finished APS correction")
        return  # return if True condition returned

    tsincr = _calc_svd_time_series(ifg_paths, params, preread_ifgs, tiles)

    ifg = Ifg(ifg_paths[0])  # just grab any for parameters in slpfilter
    ifg.open()
    spatio_temporal_filter(tsincr, ifg, params, preread_ifgs)
    ifg.close()


def spatio_temporal_filter(tsincr, ifg, params, preread_ifgs):
    """Applies a spatio-temporal filter to remove the atmospheric phase screen
    (APS) and saves the corrected interferograms. Before performing this step,
    the time series iscomputed using the SVD method. This function then performs
    temporal and spatial filtering.
    
    Args:
        tsincr (ndarray): incremental time series array of size (ifg.shape,
            nepochs-1)
        ifg (list): List of shared.Ifg class objects.
    
    Args:
      preread_ifgs: dict
      tsincr: param ifg:

    Args:
      ifg: 
      tsincr: 
      params: 
      preread_ifgs: 

    Returns:
      None, corrected interferograms are saved to disk

    """
    epochlist = mpiops.run_once(get_epochs, preread_ifgs)[0]
    # epochlist = get_epochs(preread_ifgs)[0]
    ts_lp = mpiops.run_once(temporal_low_pass_filter, tsincr, epochlist, params)
    # ts_lp = temporal_low_pass_filter(tsincr, epochlist, params)

    ts_hp = tsincr - ts_lp

    ts_aps = mpiops.run_once(spatial_low_pass_filter, ts_hp, ifg, params)
    # ts_aps = spatial_low_pass_filter(ts_hp, ifg, params)
    tsincr -= ts_aps

    mpiops.run_once(_ts_to_ifgs, tsincr, preread_ifgs)
    # _ts_to_ifgs(tsincr, preread_ifgs)


def _calc_svd_time_series(ifg_paths, params, preread_ifgs, tiles):
    """Helper function to obtain time series for spatio-temporal filter using
    SVD method
    
    Args:
        ifg_paths:
    
    Args:
      preread_ifgs: param tiles:
      ifg_paths: param params:

    Args:
      tiles: 
      ifg_paths: 
      params: 
      preread_ifgs: 

    Returns:
      

    """
    # Is there other existing functions that can perform this same job?
    log.info("Calculating time series via SVD method for " "APS correction")
    # copy params temporarily
    new_params = deepcopy(params)
    new_params[cf.TIME_SERIES_METHOD] = 2  # use SVD method

    process_tiles = mpiops.array_split(tiles)
    output_dir = params[cf.TMPDIR]

    nvels = None
    for t in process_tiles:
        log.debug("Calculating time series for tile {} during APS " "correction".format(t.index))
        ifg_parts = [shared.IfgPart(p, t, preread_ifgs, params) for p in ifg_paths]
        mst_tile = np.load(os.path.join(output_dir, "mst_mat_{}.npy".format(t.index)))
        tsincr = time_series(ifg_parts, new_params, vcmt=None, mst=mst_tile)[0]
        np.save(file=os.path.join(output_dir, "tsincr_aps_{}.npy".format(t.index)), arr=tsincr)
        nvels = tsincr.shape[2]

    nvels = mpiops.comm.bcast(nvels, root=0)
    # need to assemble tsincr from all processes
    tsincr_g = mpiops.run_once(_assemble_tsincr, ifg_paths, params, preread_ifgs, tiles, nvels)
    log.debug("Finished calculating time series for spatio-temporal filter")
    return tsincr_g


def _assemble_tsincr(ifg_paths, params, preread_ifgs, tiles, nvels):
    """Helper function to reconstruct time series images from tiles
    
    Args:
        ifg_paths:
    
    Args:
      preread_ifgs: param tiles:
      nvels: param ifg_paths:

    Args:
      ifg_paths: 
      tiles: 
      params: 
      preread_ifgs: 
      nvels: 

    Returns:
      

    """
    shape = preread_ifgs[ifg_paths[0]].shape + (nvels,)
    tsincr_g = np.empty(shape=shape, dtype=np.float32)
    for i in range(nvels):
        for n, t in enumerate(tiles):
            _assemble_tiles(i, n, t, tsincr_g[:, :, i], params[cf.TMPDIR], "tsincr_aps")

    return tsincr_g


def _ts_to_ifgs(tsincr, preread_ifgs):
    """Function that converts an incremental displacement time series into
    interferometric phase observations. Used to re-construct an interferogram
    network from a time series.

    Args:
      tsincr(ndarray): incremental time series array of size (ifg.shape,
    nepochs-1)
      preread_ifgs(dict): Dictionary of shared.PrereadIfg class instances

    Returns:
      : None, interferograms are saved to disk

    """
    log.debug("Reconstructing interferometric observations from time series")
    ifgs = list(OrderedDict(sorted(preread_ifgs.items())).values())
    _, n = get_epochs(ifgs)
    index_master, index_slave = n[: len(ifgs)], n[len(ifgs):]
    for i, ifg in enumerate(ifgs):
        phase = np.sum(tsincr[:, :, index_master[i]: index_slave[i]], axis=2)
        _save_aps_corrected_phase(ifg.path, phase)


def _save_aps_corrected_phase(ifg_path, phase):
    """Save (update) interferogram metadata and phase data after spatio-temporal
    filter (APS) correction.

    Args:
      ifg_path: param phase:
      phase: 

    Returns:

    """
    ifg = Ifg(ifg_path)
    ifg.open(readonly=False)
    ifg.phase_data[~np.isnan(ifg.phase_data)] = phase[~np.isnan(ifg.phase_data)]
    # set aps tags after aps error correction
    ifg.dataset.SetMetadataItem(ifc.PYRATE_APS_ERROR, ifc.APS_REMOVED)
    ifg.write_modified_phase()
    ifg.close()


def spatial_low_pass_filter(ts_lp, ifg, params):
    """Filter time series data spatially using either a Butterworth or Gaussian
    low pass filter defined by a cut-off distance. If the cut-off distance is
    defined as zero in the parameters dictionary then it is calculated for each
    time step using the covariance.cvd_from_phase method.
    
    Args:
        ts_lp (ndarray): Array of time series data, the result of a temporal low
            pass filter operation. shape (ifg.shape, n_epochs)
        ifg (shared.Ifg instance): interferogram object
    
    Args:
      ts_lp: param ifg:

    Args:
      ifg: 
      ts_lp: 
      params: 

    Returns:
      ndarray: ts_hp: filtered time series data of shape (ifg.shape, n_epochs)

    """
    log.info("Applying APS spatial low-pass filter")
    if params[cf.SLPF_NANFILL] == 0:
        ts_lp[np.isnan(ts_lp)] = 0  # need it here for cvd and fft
    else:
        # optionally interpolate, operation is inplace
        _interpolate_nans(ts_lp, params[cf.SLPF_NANFILL_METHOD])
    r_dist = RDist(ifg)()
    for i in range(ts_lp.shape[2]):
        ts_lp[:, :, i] = _slpfilter(ts_lp[:, :, i], ifg, r_dist, params)
    log.debug("Finished applying spatial low pass filter")
    return ts_lp


def _interpolate_nans(arr, method="linear"):
    """Fill any NaN values in arr with interpolated values. Nanfill and
    interpolation are performed in place.

    Args:
      arr: param method:  (Default value = "linear")
      method: (Default value = "linear")

    Returns:

    """
    rows, cols = np.indices(arr.shape[:2])
    for i in range(arr.shape[2]):
        a = arr[:, :, i]
        _interpolate_nans_2d(a, rows, cols, method)


def _interpolate_nans_2d(a, rows, cols, method):
    """In-place array interpolation and nanfill

    Args:
      a(ndarray): 2d ndarray to be interpolated
      rows(ndarray): 2d ndarray of row indices
      cols(ndarray): 2d ndarray of col indices
      method(str): Method; one of 'nearest', 'linear', and 'cubic'

    Returns:

    """
    a[np.isnan(a)] = griddata(
        (rows[~np.isnan(a)], cols[~np.isnan(a)]),  # points we know
        a[~np.isnan(a)],  # values we know
        (rows[np.isnan(a)], cols[np.isnan(a)]),  # points to interpolate
        method=method,
    )
    a[np.isnan(a)] = 0  # zero fill boundary/edge nans


def _slpfilter(phase, ifg, r_dist, params):
    """Wrapper function for spatial low pass filter
    
    Args:
        phase:
        ifg:
        r_dist:
    
    Args:
      phase: param ifg:
      r_dist: param params:
      ifg:

    Args:
      phase: 
      ifg: 
      r_dist: 
      params: 

    Returns:
      

    """
    if np.all(np.isnan(phase)):  # return for nan matrix
        return phase
    cutoff = params[cf.SLPF_CUTOFF]

    if cutoff == 0:
        _, alpha = cvd_from_phase(phase, ifg, r_dist, calc_alpha=True)
        cutoff = 1.0 / alpha
    rows, cols = ifg.shape
    return _slp_filter(phase, cutoff, rows, cols, ifg.x_size, ifg.y_size, params)


def _slp_filter(phase, cutoff, rows, cols, x_size, y_size, params):
    """Function to perform spatial low pass filter
    
    Args:
        phase:
        cutoff:
        rows:
        cols:
        x_size:
        y_size:
    
    Args:
      phase: param cutoff:
      rows: param cols:
      x_size: param y_size:

    Args:
      cutoff: 
      cols: 
      y_size: 
      phase: 
      rows: 
      x_size: 
      params: 

    Returns:
      

    """
    cx = np.floor(cols / 2)
    cy = np.floor(rows / 2)
    # fft for the input image
    imf = fftshift(fft2(phase))
    # calculate distance
    distfact = 1.0e3  # to convert into meters
    [xx, yy] = np.meshgrid(range(cols), range(rows))
    xx = (xx - cx) * x_size  # these are in meters as x_size in meters
    yy = (yy - cy) * y_size
    dist = np.sqrt(xx ** 2 + yy ** 2) / distfact  # km

    if params[cf.SLPF_METHOD] == 1:  # butterworth low pass filter
        H = 1.0 / (1 + ((dist / cutoff) ** (2 * params[cf.SLPF_ORDER])))
    else:  # Gaussian low pass filter
        H = np.exp(-(dist ** 2) / (2 * cutoff ** 2))
    outf = imf * H
    out = np.real(ifft2(ifftshift(outf)))
    out[np.isnan(phase)] = np.nan
    return out  # out is units of phase, i.e. mm


# TODO: use tiles here and distribute amongst processes
def temporal_low_pass_filter(tsincr, epochlist, params):
    """Filter time series data temporally using either a Gaussian, triangular or
    mean low pass filter defined by a cut-off time period (in years).
    
    Args:
        tsincr (ndarray): Array of incremental time series data of shape
            (ifg.shape, n_epochs)
        epochlist (list): List of shared.EpochList class instances
    
    Args:
      tsincr: param epochlist:

    Args:
      nepochs: 
      epochlist: 
      tsincr: 
      params: 

    Returns:
      ndarray: tsfilt_incr: filtered time series data, shape (ifg.shape,
      nepochs)

    """
    log.info("Applying APS temporal low-pass filter")
    nanmat = ~isnan(tsincr)
    tsfilt_incr = np.empty_like(tsincr, dtype=np.float32) * np.nan
    intv = np.diff(epochlist.spans)  # time interval for the neighboring epoch
    span = epochlist.spans[: tsincr.shape[2]] + intv / 2  # accumulated time
    rows, cols = tsincr.shape[:2]
    cutoff = params[cf.TLPF_CUTOFF]
    method = params[cf.TLPF_METHOD]
    threshold = params[cf.TLPF_PTHR]
    if method == 1:  # gaussian filter
        func = gauss
    elif method == 2:  # triangular filter
        func = _triangle
    else:
        func = mean_filter

    _tlpfilter(cols, cutoff, nanmat, rows, span, threshold, tsfilt_incr, tsincr, func)
    log.debug("Finished applying temporal low pass filter")
    return tsfilt_incr


# Throwaway function to define Gaussian filter weights
gauss = lambda m, yr, cutoff: np.exp(-((yr / cutoff) ** 2) / 2)


def _triangle(m, yr, cutoff):
    """Define triangular filter weights

    Args:
      m: param yr:
      cutoff: 
      yr: 

    Returns:

    """
    wgt = cutoff - abs(yr)
    wgt[wgt < 0] = 0
    return wgt


# Throwaway function to define Mean filter weights
mean_filter = lambda m, yr, cutoff: np.ones(m)


def _tlpfilter(cols, cutoff, nanmat, rows, span, threshold, tsfilt_incr, tsincr, func):
    """Wrapper function for temporal low pass filter

    Args:
      cols: param cutoff:
      nanmat: param rows:
      span: param threshold:
      tsfilt_incr: param tsincr:
      func: 
      cutoff: 
      rows: 
      threshold: 
      tsincr: 

    Returns:

    """
    for i in range(rows):
        for j in range(cols):
            sel = np.nonzero(nanmat[i, j, :])[0]  # don't select if nan
            m = len(sel)
            if m >= threshold:
                for k in range(m):
                    yr = span[sel] - span[sel[k]]
                    wgt = func(m, yr, cutoff)
                    wgt /= np.sum(wgt)
                    tsfilt_incr[i, j, sel[k]] = np.sum(tsincr[i, j, sel] * wgt)