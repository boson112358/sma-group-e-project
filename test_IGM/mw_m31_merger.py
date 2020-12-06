###### importing modules ######

import os
import matplotlib as mpl
if os.environ.get('DISPLAY','') == '' and os.name != 'nt':
    print('No display found. Using non-interactive Agg backend for matplotlib')
    mpl.use('Agg')

import numpy as np
import sys
import argparse

from amuse.community.gadget2.interface import Gadget2
from amuse.community.fi.interface import Fi

import modules.galaxies as gal
import modules.simulations as sim
import modules.data_analysis as da
import modules.igmedium.IGM_density_distribution as igm
import modules.solar_system as sol
import modules.data_analysis.solar_distance_histogram as his
from modules.progressbar import progressbar as pbar
from modules.progressbar import widgets as pbwg

from amuse.lab import units, Particles, nbody_system, read_set_from_file


###### parser for terminal usage ######

parser = argparse.ArgumentParser()
parser.add_argument('--generation', 
                    help='Generate a new galaxy model', 
                    action='store_true')
parser.add_argument('--animation', 
                    help='Allow animation output', 
                    action='store_true')
parser.add_argument('--snapshot', 
                    help='Allow simulation snapshots plots output', 
                    action='store_true')
parser.add_argument('--solar', 
                    help='Add solar system', 
                    action='store_true')
parser.add_argument('--mwsolar', 
                    help='Simulates only the MW with the Solar System', 
                    action='store_true')
parser.add_argument('--disk', 
                    help='Add test disk to MW', 
                    action='store_true')
parser.add_argument('--igm', 
                    help='Add IGM', 
                    action='store_true')
parser.add_argument('--test', 
                    help='Use test initial conditions', 
                    action='store_true')
parser.add_argument('--nomerger', 
                    help='Stop after galaxy initialization', 
                    action='store_true')
parser.add_argument('--correction', 
                    help='Correct galaxy velocity and mass', 
                    action='store_true')
parser.add_argument('-f', 
                    help='Foo value, defined for jupyter notebook compatibility')
args = parser.parse_args()

GENERATION = args.generation
ANIMATION = args.animation
SNAPSHOT = args.snapshot
SOLAR = args.solar
MWSOLAR = args.mwsolar
DISK = args.disk
IGM = args.igm
TEST = args.test
NOMERGER = args.nomerger
CORRECTION = args.correction

if ANIMATION:
    print('Animations turned on', flush=True)
if SNAPSHOT:
    print('Merger snapshot plots turned on', flush=True)

    
###### starting conditions ######
    
#Galaxies starting conditions
if not TEST:
    n_bulge = 20000
    n_disk = 20000
    n_halo = 40000
elif TEST:
    print('Using test initial conditions', flush=True)
    n_bulge = 10000
    n_disk = 20000
    n_halo = 40000

mw_parameters = {'name': 'mw',
                 #halo parameters
                 'n_halo': n_halo,
                 'halo_scale_radius': 12.96 | units.kpc,
                 #disk parameters
                 'disk_number_of_particles' : n_disk,
                 'disk_mass' : 19.66 * 2.33 * 10e9 | units.MSun,
                 'disk_scale_length' : 2.806 | units.kpc,
                 'disk_outer_radius' : 30 | units.kpc, 
                 'disk_scale_height_sech2' : 0.409 | units.kpc,
                 'disk_central_radial_velocity_dispersion': 0.7,
                 #bulge parameters
                 'bulge_scale_radius' : 0.788 | units.kpc,
                 'bulge_number_of_particles' : n_bulge,
                 #unused parameters (unclear effect)
                 "halo_streaming_fraction": 0.,
                 "bulge_streaming_fraction": 0.,
                 #unused parameters (they cause problems)
                 'disk_scale_length_of_sigR2': 2.806 | units.kpc}

m31_parameters = {'name': 'm31_not_displaced',
                  #halo parameters
                  'n_halo': n_halo,
                  'halo_scale_radius': 12.94 | units.kpc,
                  #disk parameters
                  'disk_number_of_particles' : n_disk,
                  'disk_mass' : 33.40 * 2.33 * 10e9 | units.MSun,
                  'disk_scale_length' : 5.577 | units.kpc,
                  'disk_outer_radius' : 30 | units.kpc, 
                  'disk_scale_height_sech2' : 0.3 | units.kpc,
                  'disk_central_radial_velocity_dispersion': 0.7,
                  #bulge parameters
                  'bulge_scale_radius' : 1.826 | units.kpc,
                  'bulge_number_of_particles' : n_bulge,
                  #unused parameters (unclear effect)
                  "halo_streaming_fraction": 0.,
                  "bulge_streaming_fraction": 0.,
                  #unused parameters (they cause problems)
                  'disk_scale_length_of_sigR2': 5.577 | units.kpc}

#simulation parameters
scale_mass_galaxy = 1e12 | units.MSun
scale_radius_galaxy = 80 | units.kpc
t_end = 100 | units.Myr
t_step = 5. | units.Myr

#Solar system starting conditions
n_stars = 50                                       #How many particles we will add
solar_radial_distance = 8.2
solar_position = (-np.sqrt(0.5 * solar_radial_distance**2),
                  np.sqrt(0.5 * solar_radial_distance**2),
                  0) | units.kpc                   #If we displace MW, we can do it through this vector aswell
system_radius = 0.100 | units.kpc                  #neighbourhood in which we distribute our stars
solar_tang_velocity = 220 | (units.km/units.s)     #This is roughly the velocity of solarsystem around MW
mw_velocity_vector = (0, 0, 0) | units.kms

#Intergal medium starting conditions
N1 = 5000
N2 = 1000
L = 1000 | units.kpc
Lg = 1000
rho = 770 | units.MSun / (units.kpc)**3
u = 1.6e+15 | (units.m)**2 / (units.s)**2

#M31 displacement
rotation = np.array([[0.7703,  0.3244,  0.5490],
                     [-0.6321, 0.5017,  0.5905],
                     [-0.0839, -0.8019, 0.5915]])

traslation = [-379.2, 612.7, 283.1] | units.kpc

m31_radvel_factor = 0.6
m31_transvel_factor = 0.25
radial_velocity =  m31_radvel_factor * 117 * np.array([0.4898, -0.7914, 0.3657]) | units.kms
transverse_velocity = m31_transvel_factor * 42 * np.array([0.5236, 0.6024, 0.6024]) | units.kms


###### galaxy initialization ######

converter = nbody_system.nbody_to_si(scale_mass_galaxy, scale_radius_galaxy)

if GENERATION:
    print('Generating new galaxies', flush=True)
    mw, _ = gal.make_galaxy(mw_parameters['n_halo'], converter, mw_parameters['name'], test=TEST,
                            #output dir
                            output_directory = '/data1/brentegani/',
                            #halo parameters
                            #halo_scale_radius = glxy_param['halo_scale_radius'],
                            #disk parameters
                            disk_number_of_particles = mw_parameters['disk_number_of_particles'],
                            disk_mass = mw_parameters['disk_mass'],
                            #disk_scale_length = glxy_param['disk_scale_length'],
                            #disk_outer_radius = glxy_param['disk_outer_radius'],
                            #disk_scale_height_sech2 = glxy_param['disk_scale_height_sech2'],
                            #disk_central_radial_velocity_dispersion=glxy_param['disk_central_radial_velocity_dispersion'],
                            #bulge paramaters
                            #bulge_scale_radius = glxy_param['bulge_scale_radius'],
                            bulge_number_of_particles = mw_parameters['bulge_number_of_particles'])
    
    m31_not_displaced, _ = gal.make_galaxy(m31_parameters['n_halo'], converter, m31_parameters['name'], test=TEST,
                                           #output dir
                                           output_directory = '/data1/brentegani/',
                                           #halo parameters
                                           #halo_scale_radius = glxy_param['halo_scale_radius'],
                                           #disk parameters
                                           disk_number_of_particles = m31_parameters['disk_number_of_particles'],
                                           disk_mass = m31_parameters['disk_mass'],
                                           #disk_scale_length = glxy_param['disk_scale_length'],
                                           #disk_outer_radius = glxy_param['disk_outer_radius'],
                                           #disk_scale_height_sech2 = glxy_param['disk_scale_height_sech2'],
                                           #disk_central_radial_velocity_dispersion=m31_param['disk_central_radial_velocity_dispersion'],
                                           #bulge paramaters
                                           #bulge_scale_radius = glxy_param['bulge_scale_radius'],
                                           bulge_number_of_particles = m31_parameters['bulge_number_of_particles'])
else:
    #mw, _ = gal.load_galaxy_data('mw', test=TEST)
    #m31_not_displaced, _ = gal.load_galaxy_data('m31_not_displaced', test=TEST)
    mw_data_dir = 'used_models/mw_test_2020-11-10-0001/'
    m31_data_dir = 'used_models/m31_not_displaced_test_2020-11-10-0001/'
    
    widgets = ['Found galaxy data in {}, loading: '.format(mw_data_dir), pbwg.AnimatedMarker(), pbwg.EndMsg()]
    with pbar.ProgressBar(widgets=widgets, fd=sys.stdout) as progress:
        mw = read_set_from_file(mw_data_dir + 'mw_test_2020-11-10-0001', "hdf5")
            
    widgets = ['Found galaxy data in {}, loading: '.format(m31_data_dir), pbwg.AnimatedMarker(), pbwg.EndMsg()]
    with pbar.ProgressBar(widgets=widgets, fd=sys.stdout) as progress:
        m31_not_displaced = read_set_from_file(m31_data_dir + 'm31_not_displaced_test_2020-11-10-0001', "hdf5")
    
mw_mass = da.galaxy_total_mass(mw)
m31_mass = da.galaxy_total_mass(m31_not_displaced)

if NOMERGER:
    print('Quitting after galaxy initialization')
    quit()

if CORRECTION:
    print('Correcting velocities and mass: ...', flush=True)
    vel_factor = 1/6.5
    mass_factor = 1/1000

    mw.velocity = mw.velocity * vel_factor
    m31_not_displaced.velocity =  m31_not_displaced.velocity * vel_factor

    mw.mass = mw.mass * mass_factor
    m31_not_displaced.mass =  m31_not_displaced.mass * mass_factor


###### main ######

if all(value == False for value in [MWSOLAR, DISK, IGM]):
    m31 = gal.displace_galaxy(m31_not_displaced, rotation, traslation, radial_velocity, transverse_velocity)
    
    t_end_int = int(np.round(t_end.value_in(units.Myr), decimals=0))
    t_step_int = int(np.round(t_step.value_in(units.Myr), decimals=0))
    txt_line1 = 'Simulating merger with no additional components:\n'
    txt_line2 = 't = {} Myr, t step = {}\n'.format(t_end_int, t_step_int)
    txt_line3 = 'MW mass = {}, M31 mass = {}\n'.format(mw_mass, m31_mass)
    txt_line4 = 'm31 radial velocity factor = {} * 117\n'.format(m31_radvel_factor)
    txt_line5 = 'm31 transverse velocity factor = {} * 42'.format(m31_transvel_factor)
    print(txt_line1 + txt_line2 + txt_line3 + txt_line4 + txt_line5, flush=True)
    
    if SOLAR:
        print('Adding Solar System (n = {}) ...'.format(n_stars), flush=True)
        stars = sol.make_solar_system(n_stars, solar_position, system_radius, mw_velocity_vector, solar_tang_velocity)
        stars_solver = sol.leapfrog_alg
    else:
        stars = None
        stars_solver = None

    sim.simulate_merger(mw, m31, n_halo, n_disk, n_bulge, t_end, converter, 
                        interval=5.|units.Myr, animation=ANIMATION, snapshot=SNAPSHOT, snap_freq=1000,
                        particles=stars, particles_solver=stars_solver)
    
if DISK:
    print('Simulating merger with disk test particles ...', flush=True)
    test_disk = gal.test_particles(MW, n_halo, n_bulge, n_disk)
    gal.simulate_merger_with_particles(M31, MW, converter, n_halo, n_bulge, n_disk, t_end, SCRIPT_PATH, plot=PLOT)

if MWSOLAR:
    print('Simulating MW with solar system ...', flush=True)
    mw_velocity_vector = (0, 0, 0) | units.kms
    stars = sol.make_solar_system(n_stars, solar_position, system_radius, mw_velocity_vector, solar_tang_velocity)
    sim.mw_and_stars(mw, stars, converter, n_disk, n_bulge, t_end, sol.leapfrog_alg, snapshot=SNAPSHOT)

if IGM:
    m31 = gal.displace_galaxy(m31_not_displaced, rotation, traslation, radial_velocity, transverse_velocity)
    print('Simulating merger with IGM ...', flush=True)
    print(mw.center_of_mass())
    print(m31.center_of_mass())
    widgets = ['Building IGM: ', pbwg.AnimatedMarker(), ' ',
               pbwg.Timer(), pbwg.EndMsg()]
    with pbar.ProgressBar(widgets=widgets, fd=sys.stdout) as progress:
        sph_code = igm.setup_sph_code(Fi, N1, N2, L, rho, u)
    igm.plot_igm(500,Lg,'IGM_density_0')
    
    if SOLAR:
        print('Adding Solar System (n = {}) ...'.format(n_stars), flush=True)
        stars = sol.make_solar_system(n_stars, solar_position, system_radius, mw_velocity_vector, solar_tang_velocity)
        stars_solver = sol.leapfrog_alg
    else:
        stars = None
        stars_solver = None

    sim.simulate_merger_IGM(mw, m31,sph_code, n_halo, n_disk, n_bulge, t_end, converter,
                    solver=Gadget2, interval=5|units.Myr,
                    animation=ANIMATION, snapshot=SNAPSHOT, snap_freq=5000,
                    particles=stars, particles_solver=stars_solver)
    igm.plot_igm(500,1000,'IGM_density_finished_0')
