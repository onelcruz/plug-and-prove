from src.config.loader import load_scenario_config, load_sensor_config
from src.simulator.scenario import run_simulation

SCENARIO_PATH = "config/scenarios/example_scenario.yaml"
SENSOR_PATH = "config/sensors/example_sensor.yaml"


def _load():
    scenario = load_scenario_config(SCENARIO_PATH)
    sensor = load_sensor_config(SENSOR_PATH)
    return scenario, sensor


def test_run_simulation_reproducible():
    scenario, sensor = _load()
    result_a = run_simulation(scenario, [sensor])
    result_b = run_simulation(scenario, [sensor])

    assert result_a.truth_objects == result_b.truth_objects
    assert result_a.detections_by_sensor == result_b.detections_by_sensor


def test_run_simulation_produces_all_configured_target_kinds():
    scenario, sensor = _load()
    result = run_simulation(scenario, [sensor])
    kinds = {obj.kind for obj in result.truth_objects}
    assert kinds == {"drone", "bird", "clutter"}
    assert sum(1 for obj in result.truth_objects if obj.kind == "clutter") == scenario.clutter.count


def test_run_simulation_produces_detections_for_configured_sensor():
    scenario, sensor = _load()
    result = run_simulation(scenario, [sensor])
    assert sensor.sensor_id in result.detections_by_sensor
    assert len(result.detections_by_sensor[sensor.sensor_id]) > 0


def test_different_sensors_get_independent_noise_streams():
    scenario, sensor = _load()
    sensor_2 = sensor.model_copy(update={"sensor_id": "sensor-2"})
    result = run_simulation(scenario, [sensor, sensor_2])
    detections_1 = result.detections_by_sensor[sensor.sensor_id]
    detections_2 = result.detections_by_sensor[sensor_2.sensor_id]
    # Same config, independent RNG streams -> not identical noise draws.
    assert detections_1 != detections_2
