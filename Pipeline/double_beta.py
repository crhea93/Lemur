import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astropy import units as u
from scipy.optimize import curve_fit


def _load_image(image_path):
    return np.array(fits.getdata(image_path), dtype=np.float32)


def _center_pixel_from_world(image_path, center_ra, center_dec):
    wcs = WCS(fits.getheader(image_path))
    coord = SkyCoord(center_ra * u.deg, center_dec * u.deg, frame="fk5")
    x, y = wcs.world_to_pixel(coord)
    return float(x), float(y)


def azimuthal_profile(image_path, center_pixel):
    data = _load_image(image_path)
    len_y, len_x = data.shape
    x = np.arange(len_x, dtype=np.float32) - center_pixel[0]
    y = np.arange(len_y, dtype=np.float32) - center_pixel[1]
    x_grid, y_grid = np.meshgrid(x, y)
    radius_index = np.floor(np.sqrt(x_grid**2 + y_grid**2)).astype(np.int32)

    flat_radius = radius_index.ravel()
    flat_data = data.ravel()
    counts = np.bincount(flat_radius)
    sums = np.bincount(flat_radius, weights=flat_data)
    valid = counts > 0

    radii = np.arange(len(counts), dtype=np.float32)[valid]
    profile = (sums[valid] / counts[valid]).astype(np.float32)
    return radii, profile


def double_beta_profile(radius, norm_1, core_radius_1, beta_1, norm_2, core_radius_2, beta_2, background):
    component_1 = norm_1 * (1.0 + (radius / core_radius_1) ** 2) ** (-3.0 * beta_1 + 0.5)
    component_2 = norm_2 * (1.0 + (radius / core_radius_2) ** 2) ** (-3.0 * beta_2 + 0.5)
    return component_1 + component_2 + background


def double_beta_components(radius, norm_1, core_radius_1, beta_1, norm_2, core_radius_2, beta_2, background):
    component_1 = norm_1 * (1.0 + (radius / core_radius_1) ** 2) ** (-3.0 * beta_1 + 0.5)
    component_2 = norm_2 * (1.0 + (radius / core_radius_2) ** 2) ** (-3.0 * beta_2 + 0.5)
    background_component = np.full_like(radius, background, dtype=np.float64)
    return component_1, component_2, background_component


def fit_double_beta_model(image_path, center_pixel, max_radius=None):
    radii, profile = azimuthal_profile(image_path, center_pixel=center_pixel)
    valid = np.isfinite(radii) & np.isfinite(profile)
    if max_radius is not None:
        valid &= radii <= max_radius

    fit_radii = radii[valid]
    fit_profile = profile[valid]
    if fit_radii.size < 8:
        raise ValueError('Not enough radial bins to fit the double-beta model.')

    background_guess = float(np.median(fit_profile[max(int(0.8 * fit_profile.size), 1) :]))
    signal_scale = max(float(np.max(fit_profile) - background_guess), 1e-6)
    radius_scale = max(float(fit_radii[-1]), 10.0)

    initial_guess = np.array([
        0.7 * signal_scale,
        max(radius_scale * 0.05, 3.0),
        0.7,
        0.3 * signal_scale,
        max(radius_scale * 0.2, 10.0),
        0.7,
        background_guess,
    ], dtype=np.float64)
    lower_bounds = np.array([0.0, 1e-3, 0.34, 0.0, 1e-3, 0.34, np.min(fit_profile)], dtype=np.float64)
    upper_bounds = np.array([
        np.inf,
        max(radius_scale * 2.0, 10.0),
        3.0,
        np.inf,
        max(radius_scale * 2.0, 10.0),
        3.0,
        np.max(fit_profile),
    ], dtype=np.float64)

    fit_weights = np.sqrt(np.clip(np.abs(fit_profile), a_min=1e-6, a_max=None))
    best_fit, _ = curve_fit(
        double_beta_profile,
        fit_radii,
        fit_profile,
        p0=initial_guess,
        bounds=(lower_bounds, upper_bounds),
        sigma=fit_weights,
        absolute_sigma=False,
        maxfev=50000,
    )
    return fit_radii, fit_profile, best_fit


def plot_double_beta_fit(image_path, output_path, center_pixel, max_radius=None):
    fit_radii, fit_profile, best_fit = fit_double_beta_model(
        image_path,
        center_pixel=center_pixel,
        max_radius=max_radius,
    )
    component_1, component_2, background_component = double_beta_components(fit_radii, *best_fit)
    model_profile = component_1 + component_2 + background_component
    radius_3rc2 = 3.0 * best_fit[4]

    figure, axis = plt.subplots(figsize=(8, 5))
    axis.plot(fit_radii, fit_profile, color='black', linewidth=1.0, label='Profile')
    axis.plot(fit_radii, model_profile, color='tab:red', linewidth=2.0, label='Double-beta fit')
    axis.plot(fit_radii, component_1 + background_component, color='tab:blue', linestyle='--', linewidth=1.5, label='Component 1 + background')
    axis.plot(fit_radii, component_2 + background_component, color='tab:green', linestyle='--', linewidth=1.5, label='Component 2 + background')
    axis.plot(fit_radii, background_component, color='tab:gray', linestyle=':', linewidth=1.2, label='Background')
    axis.axvline(radius_3rc2, color='tab:purple', linestyle='-.', linewidth=1.3, label='3 x rc2')
    axis.set_xlabel('Radius (pixels)')
    axis.set_ylabel('Azimuthal mean surface brightness')
    axis.set_yscale('log')
    axis.legend()
    axis.set_title('Double-beta fit to radial profile')
    parameter_text = "\n".join([
        rf'$A_1 = {best_fit[0]:.3g}$',
        rf'$r_{{c,1}} = {best_fit[1]:.3g}$',
        rf'$\beta_1 = {best_fit[2]:.3g}$',
        rf'$A_2 = {best_fit[3]:.3g}$',
        rf'$r_{{c,2}} = {best_fit[4]:.3g}$',
        rf'$3r_{{c,2}} = {radius_3rc2:.3g}$',
        rf'$\beta_2 = {best_fit[5]:.3g}$',
        rf'$b_{{\mathrm{{kg}}}} = {best_fit[6]:.3g}$',
    ])
    axis.text(
        0.98,
        0.98,
        parameter_text,
        transform=axis.transAxes,
        ha='right',
        va='top',
        fontsize=9,
        bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.85},
    )
    figure.tight_layout()
    os.makedirs(os.path.dirname(os.fspath(output_path)) or '.', exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)
    return best_fit


def run_double_beta_fit(cluster_name, image_path, db_service, output_dir, max_radius=None):
    center_record = db_service.get_center(cluster_name)
    if center_record is None:
        raise RuntimeError(f'No canonical center available for cluster {cluster_name}.')
    center_ra = center_record.get('center_ra')
    center_dec = center_record.get('center_dec')
    if center_ra is None or center_dec is None:
        raise RuntimeError(f'Canonical center for {cluster_name} is missing RA/DEC.')

    center_x, center_y = _center_pixel_from_world(image_path, center_ra, center_dec)
    plot_path = Path(output_dir) / 'double_beta_fit.png'
    best_fit = plot_double_beta_fit(
        image_path=image_path,
        output_path=plot_path,
        center_pixel=(center_x, center_y),
        max_radius=max_radius,
    )
    db_service.upsert_double_beta_fit(
        cluster_name,
        norm_1=float(best_fit[0]),
        core_radius_1=float(best_fit[1]),
        beta_1=float(best_fit[2]),
        norm_2=float(best_fit[3]),
        core_radius_2=float(best_fit[4]),
        beta_2=float(best_fit[5]),
        background=float(best_fit[6]),
        triple_core_radius_2=float(3.0 * best_fit[4]),
        center_x=float(center_x),
        center_y=float(center_y),
        image_path=str(Path(image_path)),
        plot_path=str(plot_path),
        max_radius=max_radius,
    )
    return {
        'best_fit': best_fit,
        'plot_path': str(plot_path),
        'center_x': center_x,
        'center_y': center_y,
    }
