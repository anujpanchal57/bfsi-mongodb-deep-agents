WS := accrual-variance-review

.PHONY: install test seed validate reset smoke diagnose ui validate-agent dev deploy deploy-auto atlas-setup memory-configure memory-apply memory-status

install:
	cd $(WS) && uv sync --extra ui --extra test

test:
	cd $(WS) && uv run pytest -q

seed:
	cd $(WS) && uv run python scripts/seed_mock_data.py --dataset-version v1 --reset

validate:
	cd $(WS) && uv run python scripts/validate_seed.py --workspace-id accrual_review_demo_2026_06

reset:
	cd $(WS) && uv run python scripts/reset_demo.py --workspace-id accrual_review_demo_2026_06 --confirm

smoke:
	cd $(WS) && uv run python scripts/smoke_demo.py

diagnose:
	cd $(WS) && uv run python scripts/diagnose.py

ui:
	cd $(WS) && uv run streamlit run src/ui/app.py

# --- platform (agentengine CLI; one-time: download CLI, agentengine auth login) ---
# agentengine commands run from the workspace dir; memory config is read from
# project-config.yaml at the project root.
validate-agent:
	cd $(WS) && agentengine agent validate --strict

atlas-setup:
	cd $(WS) && agentengine atlas setup

dev:
	cd $(WS) && agentengine dev up

deploy:
	cd $(WS) && agentengine build && agentengine deploy

deploy-auto:
	cd $(WS) && agentengine deploy --auto

memory-configure:
	agentengine memory configure

memory-apply:
	agentengine memory apply

memory-status:
	agentengine memory status
