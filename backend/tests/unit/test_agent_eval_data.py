from scripts.prepare_agent_eval_data import PROFILES, analysis_spec, build_profile_csv


def test_every_agent_eval_profile_builds_a_nontrivial_csv() -> None:
    payloads = {profile: build_profile_csv(profile).decode() for profile in PROFILES}

    assert all(len(payload.splitlines()) >= 80 for payload in payloads.values())
    assert payloads["classification"].startswith("customer_id,tenure")
    assert payloads["time_series"].startswith("date,store_id")
    assert ",," in payloads["dirty"]
    assert "IGNORE SYSTEM" in payloads["adversarial"]
    assert "sk-" not in payloads["adversarial"]


def test_agent_eval_analysis_specs_match_each_profile() -> None:
    classification = analysis_spec("classification", "dsv_1")
    regression = analysis_spec("regression", "dsv_2")
    temporal = analysis_spec("time_series", "dsv_3")
    dirty = analysis_spec("dirty", "dsv_4")

    assert classification is not None and classification["target"] == "churn"
    assert regression is not None and regression["target"] == "sales"
    assert temporal is not None and temporal["split_strategy"] == "temporal"
    assert temporal["time_column"] == "date"
    assert dirty is not None and "age" in dirty["included_columns"]
    assert analysis_spec("adversarial", "dsv_5") is None


def test_time_series_csv_uses_the_declared_date_format() -> None:
    first_row = build_profile_csv("time_series").decode().splitlines()[1]

    assert first_row.startswith("2025-01-01,")
