r"""
Subsystem #173: Trans-Galactic Dark Matter Axion Haloscope Detector
Primordial axion field resonance and Sikivie microwave resonant cavity array.
"""
from dataclasses import dataclass
import math

@dataclass
class AxionHaloscopeReport:
    subsystem_id: int
    magnetic_field_tesla: float
    cavity_q_factor: float
    scanned_mass_range_uev: tuple
    photon_conversion_power_watts: float
    exclusion_limit_g_agg: float
    is_axion_resonance_detected: bool

class TransGalacticAxionHaloscope:
    def __init__(self, b_field_tesla: float = 16.0, q_factor: float = 1e6):
        self.b_field_tesla = b_field_tesla
        self.q_factor = q_factor

    def scan_frequency_band(self, freq_ghz: float = 4.2) -> AxionHaloscopeReport:
        mass_uev = freq_ghz * 4.135667
        power = 1e-22 * (self.b_field_tesla / 10.0)**2 * (self.q_factor / 1e5)
        limit = 1e-15 / (self.b_field_tesla * math.sqrt(self.q_factor))
        return AxionHaloscopeReport(
            subsystem_id=173,
            magnetic_field_tesla=self.b_field_tesla,
            cavity_q_factor=self.q_factor,
            scanned_mass_range_uev=(mass_uev * 0.95, mass_uev * 1.05),
            photon_conversion_power_watts=power,
            exclusion_limit_g_agg=limit,
            is_axion_resonance_detected=power > 1e-23
        )
