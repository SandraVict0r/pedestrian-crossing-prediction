#!/usr/bin/env python

# Script CARLA / Unreal Engine pour exécuter UN SEUL trial.
# Il :
#  - se connecte au serveur CARLA
#  - configure la météo et les conditions du trial
#  - spawn un véhicule + décor (selon exp)
#  - pilote le véhicule jusqu’à la fin du trajet
#  - détecte la vitesse cible, la distance et l’événement de disparition
# Ce script est appelé pour chaque trial dans une session complète.

# ------------------------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------------------------

# Librairies standards
import sys
import threading
import time
import math
import argparse
import logging

# Windows beep (signal sonore)
import winsound

# Random pour le choix de blueprint
from numpy import random

# API CARLA
import carla

# Agents de navigation CARLA
from agents.navigation.basic_agent import BasicAgent
from agents.navigation.behavior_agent import BehaviorAgent

# ------------------------------------------------------------------------------
# CONFIGURATION DES POSITIONS ET BLUEPRINTS
# ------------------------------------------------------------------------------

# Liste de positions possibles du "player" (piéton ou référence)
# Ces positions déterminent l’orientation et la direction du véhicule.
Player_Location = [
    carla.Location(x=14343.0, y=30909.0, z=0.0),
    carla.Location(x=2665.0, y=29887.0, z=0.0),
    carla.Location(x=13317.0, y=11258.0, z=0.0)
]

# Mapping (météo → blueprint véhicule)
Weather_bp = {
    str([False,False,False]): 'vehicle.ue4.chevrolet.impala',
    str([False,False,True]):  'vehicle.dodge.charger',
    str([True,True,False]):   'vehicle.taxi.ford'
}

# Blueprints du "player", dépendant de la position
Player_bp = [
    'vehicle.ue4.audi.tt',
    'vehicle.nissan.patrol',
    'vehicle.ue4.mercedes.ccc'
]

# Différents types de véhicules pour le trial
Vehicle_bp = {
    "normal": 'vehicle.lincoln.mkz',
    "truck":  'vehicle.sprinter.mercedes',
    "city":   'vehicle.mini.cooper'
}

# ------------------------------------------------------------------------------
# FONCTIONS UTILES
# ------------------------------------------------------------------------------

def get_speed(actor):
    """Calcule la vitesse d’un acteur CARLA en km/h."""
    velocity = actor.get_velocity()
    speed = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
    return speed * 3.6

def get_distance_to_player(vehicle_location, player_location):
    """Distance véhicule → joueur, divisée par 100 (conversion de ton setup)."""
    return math.sqrt(
        (vehicle_location.x - player_location.x) ** 2 +
        (vehicle_location.y - player_location.y) ** 2 +
        (vehicle_location.z - player_location.z) ** 2) / 100

def beep():
    """Petit beep sonore utilisé comme marqueur d'événement."""
    winsound.Beep(900,500)

def get_actor_blueprints(world, filter, generation):
    """
    Filtre les blueprints CARLA par nom et génération.
    Utilisé pour sélectionner le modèle de véhicule.
    """
    bps = world.get_blueprint_library().filter(filter)

    if generation.lower() == "all":
        return bps

    if len(bps) == 1:
        return bps

    try:
        int_generation = int(generation)
        if int_generation in [1, 2, 3]:
            return [x for x in bps if int(x.get_attribute('generation')) == int_generation]
        else:
            print("Warning: invalid actor generation.")
            return []
    except:
        print("Warning: invalid actor generation.")
        return []

# ------------------------------------------------------------------------------
# FONCTION PRINCIPALE – 1 TRIAL
# ------------------------------------------------------------------------------

def main():
    # --------------------------------------------------------------------------
    # ARGUMENTS DU TRIAL
    # --------------------------------------------------------------------------
    # Les paramètres du trial (météo, vitesse, position, etc.) sont passés
    # via la ligne de commande. C’est ce que ton script de session modifiera.
    argparser = argparse.ArgumentParser(description=__doc__)
    
    # IP / Port CARLA
    argparser.add_argument('--host', metavar='H', default='127.0.0.1')
    argparser.add_argument('-p', '--port', default=2000, type=int)

    # Vitesse cible du trial
    argparser.add_argument('-v', '--velocity', default=50, type=int)

    # Conditions météo
    argparser.add_argument('-l', '--lights', default=False, type=bool)
    argparser.add_argument('-c', '--clouds', default=False, type=bool)
    argparser.add_argument('-r', '--rain',   default=False, type=bool)

    # Distance où le véhicule doit disparaître (condition de fin)
    argparser.add_argument('-d', '--disappear', default=-50.0, type=float)

    # Position du player (index 0-1-2)
    argparser.add_argument('-pos', '--position', default=0, type=int)

    # Type de véhicule pour le trial
    argparser.add_argument('-bp', '--filterv', default='normal')

    # Moteur CARLA / Traffic Manager
    argparser.add_argument('--generationv', default='All')
    argparser.add_argument('--tm-port', default=8000, type=int)
    argparser.add_argument('--asynch', action='store_true')
    argparser.add_argument('--hybrid', action='store_true')
    argparser.add_argument('-s', '--seed', type=int)
    argparser.add_argument('--seedw', default=0, type=int)

    # Mode "hero" / respawn / rendering
    argparser.add_argument('--hero', action='store_true', default=False)
    argparser.add_argument('--respawn', action='store_true', default=False)
    argparser.add_argument('--no-rendering', action='store_true', default=False)

    args = argparser.parse_args()

    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)

    # --------------------------------------------------------------------------
    # CONNEXION AU SERVEUR CARLA
    # --------------------------------------------------------------------------
    vehicles_list = []
    client = carla.Client(args.host, args.port)
    client.set_timeout(10.0)

    # Mode synchro / async
    synchronous_master = False

    # Seed pour comportement déterministe
    random.seed(args.seed if args.seed is not None else int(time.time()))

    try:
        world = client.get_world()
        actors = world.get_actors()

        # Traffic Manager
        traffic_manager = client.get_trafficmanager(args.tm_port)
        traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        if args.respawn:
            traffic_manager.set_respawn_dormant_vehicles(True)
        if args.hybrid:
            traffic_manager.set_hybrid_physics_mode(True)
            traffic_manager.set_hybrid_physics_radius(70.0)
        if args.seed is not None:
            traffic_manager.set_random_device_seed(args.seed)

        settings = world.get_settings()

        # ----------------------------------------------------------------------
        # MÉTÉO DU TRIAL
        # ----------------------------------------------------------------------
        if args.rain:
            weather = carla.WeatherParameters.MidRainyNoon
        else:
            weather = carla.WeatherParameters.ClearNoon

        weather.cloudiness = 100.0 if args.clouds else 25.0

        world.set_weather(weather)

        # ----------------------------------------------------------------------
        # MODE SYNCHRONE POUR LA PHYSIQUE
        # ----------------------------------------------------------------------
        if not args.asynch:
            traffic_manager.set_synchronous_mode(True)
            if not settings.synchronous_mode:
                synchronous_master = True
                settings.synchronous_mode = True
        else:
            print("Running in asynchronous mode")

        if args.no_rendering:
            settings.no_rendering_mode = True

        settings.fixed_delta_seconds = None
        world.apply_settings(settings)

        # ----------------------------------------------------------------------
        # SÉLECTION DES BLUEPRINTS SELON LES PARAMÈTRES
        # ----------------------------------------------------------------------
        blueprint = get_actor_blueprints(world, Vehicle_bp[args.filterv], args.generationv)[0]
        weather_blueprint = get_actor_blueprints(world, Weather_bp[str([args.rain,args.clouds,args.lights])], args.generationv)[0]
        player_blueprint = get_actor_blueprints(world, Player_bp[args.position], args.generationv)[0]

        spawn_points = world.get_map().get_spawn_points()

        # Commandes CARLA pour spawn
        SpawnActor = carla.command.SpawnActor
        SetAutopilot = carla.command.SetAutopilot
        FutureActor = carla.command.FutureActor

        # ----------------------------------------------------------------------
        # SPAWN DES 3 ACTEURS DU TRIAL :
        #   - véhicule autopiloté
        #   - décor lié à la météo
        #   - "player" (véhicule statique)
        # ----------------------------------------------------------------------

        batch = []

        # Choix de driver aléatoire
        if blueprint.has_attribute('driver_id'):
            driver_id = random.choice(blueprint.get_attribute('driver_id').recommended_values)
            blueprint.set_attribute('driver_id', driver_id)

        player_location = Player_Location[args.position]

        # Définition du start/end en fonction de la position du player
        if args.position == 0:
            target_distance = player_location.x - args.disappear * 100
            start = 4
            end = 13
        elif args.position == 1:
            target_distance = player_location.x + args.disappear * 100
            start = 16
            end = 99
        else:
            target_distance = player_location.x - args.disappear * 100
            start = 9
            end = 22

        # Spawn principal
        batch.append(
            SpawnActor(blueprint, spawn_points[start])
            .then(SetAutopilot(FutureActor, True, traffic_manager.get_port()))
        )
        batch.append(SpawnActor(weather_blueprint, spawn_points[61]))
        batch.append(SpawnActor(player_blueprint, spawn_points[71]))

        results = client.apply_batch_sync(batch, synchronous_master)

        # Vérification d’erreurs de spawn
        if results[0].error:
            logging.error(results[0].error)
        else:
            vehicle_id = results[0].actor_id
            vehicle = world.get_actor(vehicle_id)
            vehicles_list.append(vehicle_id)
            vehicles_list += [results[1].actor_id, results[2].actor_id]
            print(f"Vehicle spawned with ID: {vehicle_id}")

        # ----------------------------------------------------------------------
        # CONFIGURATION DE L’AGENT (BasicAgent)
        # ----------------------------------------------------------------------
        agent = BasicAgent(vehicle)
        final_point = spawn_points[end].location
        agent.set_destination(final_point)
        agent.set_target_speed(args.velocity)
        agent.follow_speed_limits(False)
        agent.ignore_stop_signs(True)
        agent.ignore_traffic_lights(True)

        # Premier tick pour stabiliser la scène
        if args.asynch or not synchronous_master:
            world.wait_for_tick()
        else:
            world.tick()

        print('spawned %d vehicles, press Ctrl+C to exit.' % (len(vehicles_list)))

        # Gestion des lumières
        lmanager = world.get_lightmanager()
        mylights = lmanager.get_all_lights()

        if args.lights:
            lmanager.turn_on(mylights)
            lmanager.set_color(mylights, carla.Color(125, 100, 80))
            vehicle.set_light_state(carla.VehicleLightState.All)
        else:
            lmanager.turn_off(mylights)
            lmanager.set_color(mylights, carla.Color(0, 0, 0))
            vehicle.set_light_state(carla.VehicleLightState.Position)

        # Flags de contrôle
        tolerance = 0.5
        near_target_speed_reached = False
        near_target_distance = False
        beeped = False

        # ----------------------------------------------------------------------
        # BOUCLE PRINCIPALE DU TRIAL
        # ----------------------------------------------------------------------
        while True:

            # Tick du monde (synchro / async)
            if not args.asynch and synchronous_master:
                world.tick()
            else:
                world.wait_for_tick()

            # Si l’agent a atteint la destination
            if agent.done():
                break

            # Calcul de la commande de conduite
            control = agent.run_step()
            vehicle.apply_control(control)

            # Position et vitesse du véhicule
            vehicle_transform = vehicle.get_transform()
            vehicle_location = vehicle_transform.location
            distance = get_distance_to_player(vehicle_location * 100, player_location)
            speed = get_speed(vehicle)

            # Condition de disparition du véhicule
            if args.disappear >= 0.0:
                sys.stdout.write('\r' + f"Vehicle at x = {vehicle_location.x*100:.2f}")
                sys.stdout.flush()

                if args.position == 1:
                    if not near_target_distance and vehicle_location.x * 100 <= target_distance:
                        print(f"\nDisappearing at = {distance:.2f} meters")
                        break
                else:
                    if not near_target_distance and vehicle_location.x * 100 >= target_distance:
                        print(f"\nDisappearing at = {distance:.2f} meters")
                        break

            # Détection de la vitesse cible
            if not near_target_speed_reached and abs(speed - agent._target_speed) <= tolerance:
                threading.Thread(target=beep).start()
                distance_to_player = get_distance_to_player(vehicle_location * 100, player_location)
                print(f"\nNear target speed ({speed} km/h), Distance to player = {distance_to_player:.2f} m")
                near_target_speed_reached = True

            # Affichage continu de la vitesse
            sys.stdout.write('\r' + f"Vehicle speed: {speed:.2f} km/h")
            sys.stdout.flush()

    finally:
        # Nettoyage du mode synchro/rendu
        if not args.asynch and synchronous_master:
            settings = world.get_settings()
            settings.synchronous_mode = False
            settings.no_rendering_mode = False
            settings.fixed_delta_seconds = None
            world.apply_settings(settings)

        # Destruction des acteurs
        print('\ndestroying %d vehicles' % len(vehicles_list))
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles_list])

        time.sleep(0.5)

# ------------------------------------------------------------------------------
# ENTRYPOINT
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print('\ndone.')
