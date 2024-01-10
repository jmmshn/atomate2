from __future__ import annotations


def test_electrode_makers(mock_vasp, clean_dir, test_dir):
    from jobflow import OutputReference, run_locally
    from pymatgen.core import Structure

    from atomate2.vasp.flows.core import RelaxMaker, StaticMaker
    from atomate2.vasp.flows.electrode import ElectrodeInsertionMaker
    from atomate2.vasp.powerups import (
        update_user_incar_settings,
        update_user_kpoints_settings,
    )
    from atomate2.vasp.sets.mp import (
        MPMetaGGARelaxSetGenerator,
        MPMetaGGAStaticSetGenerator,
    )

    # mapping from job name to directory containing test files
    ref_paths = {
        "relax": "H_Graphite/relax",
        "relax 0 (0)": "H_Graphite/relax_0_(0)",
        "relax 1 (0)": "H_Graphite/relax_1_(0)",
        "relax 1 (1)": "H_Graphite/relax_1_(1)",
        "relax 1 (2)": "H_Graphite/relax_1_(2)",
        "static 0": "H_Graphite/static_0",
        "static 1": "H_Graphite/static_1",
    }

    fake_run_vasp_kwargs = {
        "relax": {
            "incar_settings": ["NSW", "ISIF"],
            "check_inputs": ["incar", "poscar"],
        },
        "relax 0 (0)": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
        "relax 1 (0)": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
        "relax 1 (1)": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
        "relax 1 (2)": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
        "static 0": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
        "static 1": {"incar_settings": ["NSW"], "check_inputs": ["incar"]},
    }

    # automatically use fake VASP and write POTCAR.spec during the test
    mock_vasp(ref_paths, fake_run_vasp_kwargs)

    # create the workflow
    struct = Structure.from_file(test_dir / "vasp/H_Graphite/C4.vasp")
    single_relax_maker = RelaxMaker(input_set_generator=MPMetaGGARelaxSetGenerator())
    static_maker = StaticMaker(
        input_set_generator=MPMetaGGAStaticSetGenerator(), task_document_kwargs={}
    )

    maker = ElectrodeInsertionMaker(
        relax_maker=single_relax_maker, static_maker=static_maker
    )
    flow = maker.make(struct, inserted_element="H", n_steps=2)

    flow = update_user_kpoints_settings(flow, {"grid_density": 88})
    flow = update_user_incar_settings(
        flow, {"NGX": 18, "NGY": 18, "NGZ": 60, "ISIF": 2, "EDIFFG": -0.1}
    )

    # run the flow or job and ensure that it finished running successfully
    responses = run_locally(flow, create_folders=True, ensure_success=True)

    inserted_formulas = []
    for res in responses.values():
        for r in res.values():
            if not isinstance(r.output, OutputReference) and hasattr(
                r.output, "formula_pretty"
            ):
                inserted_formulas.append(  # noqa: PERF401
                    f"{r.output.formula_pretty}-{r.output.task_label.split()[0]}"
                )
    inserted_formulas.sort()
    # C-relax, C-static
    # HC4-relax (1x first insertion)
    # HC4-static
    # HC2-relax, (3x second insertion)
    assert inserted_formulas == [
        "C-relax",
        "C-static",
        "HC2-relax",
        "HC2-relax",
        "HC2-relax",
        "HC4-relax",
        "HC4-static",
    ]
