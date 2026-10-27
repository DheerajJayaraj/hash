"""Run the illustrative roller-construction comparison."""

from dac_sim.roller_comparison import compare_roller_options


def main():
    results = compare_roller_options(
        outer_diameter_m=0.15,
        face_width_m=0.22,
        wall_thickness_m=0.01,
        initial_temperature_k=298.15,
        target_temperature_k=378.15,
        heater_power_w=500.0,
    )

    print("\nIllustrative roller comparison")
    print("Assumed material properties; ideal heating only.\n")

    for result in results:
        print(f"Configuration: {result['configuration']}")
        print(f"  Metal mass: {result['metal_mass_kg']:.3f} kg")
        print(f"  Fluid mass: {result['fluid_mass_kg']:.3f} kg")
        print(
            "  Heat capacity: "
            f"{result['heat_capacity_j_k']:.1f} J/K"
        )
        print(
            "  Ideal heating energy: "
            f"{result['ideal_heating_energy_j'] / 1000:.2f} kJ"
        )
        print(
            "  Ideal heating time: "
            f"{result['ideal_heating_time_s']:.1f} s"
        )
        print()


if __name__ == "__main__":
    main()
