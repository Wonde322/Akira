import json
import subprocess
import sys


def test_frozen_desktop_persists_all_service_data_outside_the_bundle(tmp_path):
    script = '''
import json, sys
from pathlib import Path
import config, desktop
root = Path(sys.argv[1])
desktop.sys.frozen = True
desktop.Path.home = staticmethod(lambda: root)
desktop._redirect_paths()
import scheduler, task_runtime, event_bus, awareness, proactive_inbox
import context_rule_store, goal_context, proactive_action_lifecycle
from proactive_feedback import ProactiveFeedbackStore
from proactive_attention_budget import ProactiveAttentionBudget
from proactive_interruption_control import ProactiveInterruptionControl
paths = [scheduler.SCHEDULE_FILE, task_runtime.TASK_FILE, event_bus.EVENT_LOG,
 awareness.STATE_FILE, proactive_inbox.INBOX_FILE, context_rule_store.DEFAULT_RULES_FILE,
 goal_context.GOALS_FILE, proactive_action_lifecycle.DEFAULT_FILE,
 ProactiveFeedbackStore().path, ProactiveAttentionBudget().path,
 ProactiveInterruptionControl().path]
print(json.dumps([str(path) for path in paths]))
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, text=True, check=True, timeout=10)
    expected = tmp_path / 'Library' / 'Application Support' / 'Akira' / 'runtime'
    from pathlib import Path
    assert all(Path(path).is_relative_to(expected) for path in json.loads(result.stdout))
