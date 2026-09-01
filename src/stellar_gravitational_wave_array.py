r"""
Subsystem #170: Stellar-Mass Gravitational Wave Interferometer Array
Space-based nano-Hz and micro-Hz cosmological spacetime metric tensor survey.
"""
from dataclasses import dataclass
import math

@dataclass
class GravitationalWaveSurveyReport:
    subsystem_id: int
    arm_length_gigameters: float
    strain_sensitivity_h: float
    tracked_merger_events: int
    metric_tensor_perturbation_norm: float
    spatial_triangulation_accuracy_arcsec: float

class StellarGravitationalWaveArray:
    def __init__(self, arm_length_gm: float = 5.0):
        self.arm_length_gm = arm_length_gm

    def survey_metric_perturbations(self, integration_hours: float = 24.0) -> GravitationalWaveSurveyReport:
        sensitivity = 1e-22 / math.sqrt(self.arm_length_gm * integration_hours)
        events = int(142 * math.log1p(integration_hours))
        return GravitationalWaveSurveyReport(
            subsystem_id=170,
            arm_length_gigameters=self.arm_length_gm,
            strain_sensitivity_h=sensitivity,
            tracked_merger_events=events,
            metric_tensor_perturbation_norm=sensitivity * 1.42,
            spatial_triangulation_accuracy_arcsec=0.0042 / math.sqrt(self.arm_length_gm)
        )
