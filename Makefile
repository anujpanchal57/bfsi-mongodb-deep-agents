.PHONY: install install-platform test seed validate reset smoke diagnose ui validate-agent dev deploy

install:
	pip install -e ".[ui,test]"

install-platform:
	pip install -e ".[platform]"

test:
	pytest -q

seed:
	python scripts/seed_mock_data.py --dataset-version v1 --reset

validate:
	python scripts/validate_seed.py --workspace-id accrual_review_demo_2026_06

reset:
	python scripts/reset_demo.py --workspace-id accrual_review_demo_2026_06 --confirm

smoke:
	python scripts/smoke_demo.py

diagnose:
	python scripts/diagnose.py

ui:
	streamlit run src/ui/app.py

# --- platform (agentengine CLI) ---
validate-agent:
	agentengine agent validate

dev:
	agentengine dev up

deploy:
	agentengine build && agentengine deploy
