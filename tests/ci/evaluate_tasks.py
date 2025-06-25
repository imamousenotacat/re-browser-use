"""
Runs all agent tasks in parallel SEQUENTIALLY I'M A POOR MOUSE (up to 10 at a time) using separate subprocesses.
Each task gets its own Python process, preventing browser session interference.
Does not fail on partial failures (always exits 0).
"""

import argparse
import asyncio
import glob
import json
import os
import sys

import datetime

import aiofiles
import yaml
from pydantic import BaseModel

from browser_use.agent.views import AgentHistoryList
from patchright.async_api import async_playwright as async_patchright
from tests.utils_for_tests import create_browser_session, create_agent, create_llm

# --- CONFIG ---
MAX_PARALLEL = 10
TASK_DIR = (
	sys.argv[1]
	if len(sys.argv) > 1 and not sys.argv[1].startswith('--')
	else os.path.join(os.path.dirname(__file__), '../agent_tasks')
)
TASK_FILES = glob.glob(os.path.join(TASK_DIR, '*.yaml'))
HEADLESS_EVALUATION = os.environ.get('HEADLESS_EVALUATION', 'True').lower() == 'true'

async def _stream_reader(stream, buffer, print_stream):
	"""Reads from a stream, buffers the output, and prints it in real-time."""
	while True:
		line = await stream.readline()
		if not line:
			break
		buffer.append(line)
		timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-4]
		print(f"[{timestamp}] {line.decode(errors='ignore').strip()}", file=print_stream, flush=True)


class JudgeResponse(BaseModel):
	success: bool
	explanation: str


async def run_single_task(task_file):
	"""Run a single task in the current process (called by subprocess)"""
	try:
		print(f'[DEBUG] Starting task: {os.path.basename(task_file)}', file=sys.stderr)

		# Being blind it's a terrible thing :-( ...
		# if not SHOW_LOGS_AND_HEADFUL:
		# 	# Suppress all logging in subprocess to avoid interfering with JSON output
		# 	logging.getLogger().setLevel(logging.CRITICAL)
		# 	for logger_name in ['browser_use', 'telemetry', 'message_manager']:
		# 		logging.getLogger(logger_name).setLevel(logging.CRITICAL)
		# 	warnings.filterwarnings('ignore')

		print('[DEBUG] Loading task file...', file=sys.stderr)
		async with aiofiles.open(task_file, 'r') as f:
			content = await f.read()
		task_data = yaml.safe_load(content)
		task = task_data['task']
		judge_context = task_data.get('judge_context', ['The agent must solve the task'])
		max_steps = task_data.get('max_steps', 15)

		print(f'[DEBUG] Task: {task[:100]}...', file=sys.stderr)
		print(f'[DEBUG] Max steps: {max_steps}', file=sys.stderr)

		agent_llm = create_llm()
		judge_llm = create_llm()
		print('[DEBUG] LLMs initialized', file=sys.stderr)

		# Each subprocess gets its own profile and session
		print('[DEBUG] Creating browser session...', file=sys.stderr)
		playwright = await async_patchright().start()
		session = await create_browser_session(playwright, headless=HEADLESS_EVALUATION)
		print('[DEBUG] Browser session created', file=sys.stderr)

		# => UNNEEDED start() CALL AND ERROR CHECKING: ALL THAT IS NEEDED TO HAVE A CLEAN AND PURE patchright STEALTH BROWSER IS ALREADY INITIALIZED ....
		#    There will be a call to BrowserSession.start() later in Agent.run but the bulk of the work has already been done here by create_browser_session
		# Test if browser is working
		# try:
		# 	await session.start()
		# 	page = await session.create_new_tab()
		# 	print('[DEBUG] Browser test: page created successfully', file=sys.stderr)
		# 	await page.goto('https://httpbin.org/get', timeout=10000)
		# 	print('[DEBUG] Browser test: navigation successful', file=sys.stderr)
		# 	title = await page.title()
		# 	print(f"[DEBUG] Browser test: got title '{title}'", file=sys.stderr)
		# except Exception as browser_error:
		# 	print(f'[DEBUG] Browser test failed: {str(browser_error)}', file=sys.stderr)
		# 	print(f'[DEBUG] Browser error type: {type(browser_error).__name__}', file=sys.stderr)

		print('[DEBUG] Starting agent execution...', file=sys.stderr)
		agent = await create_agent(task=task, llm=agent_llm, browser_session=session)

		try:
			history: AgentHistoryList = await agent.run(max_steps=max_steps)
			print('[DEBUG] Agent.run() returned successfully', file=sys.stderr)
		except Exception as agent_error:
			print(f'[DEBUG] Agent.run() failed with error: {str(agent_error)}', file=sys.stderr)
			print(f'[DEBUG] Error type: {type(agent_error).__name__}', file=sys.stderr)
			# Re-raise to be caught by outer try-catch
			raise agent_error

		agent_output = history.final_result() or ''
		print('[DEBUG] Agent execution completed', file=sys.stderr)

		# Test if LLM is working by making a simple call
		try:
			test_response = await agent_llm.ainvoke("Say 'test'")
			print(f'[DEBUG] LLM test call successful: {test_response.content[:50]}', file=sys.stderr)
		except Exception as llm_error:
			print(f'[DEBUG] LLM test call failed: {str(llm_error)}', file=sys.stderr)

		# Debug: capture more details about the agent execution
		total_steps = len(history.history) if hasattr(history, 'history') else 0
		last_action = history.history[-1] if hasattr(history, 'history') and history.history else None
		debug_info = f'Steps: {total_steps}, Final result length: {len(agent_output)}'
		if last_action:
			debug_info += f', Last action: {type(last_action).__name__}'

		# Log to stderr so it shows up in GitHub Actions (won't interfere with JSON output to stdout)
		print(f'[DEBUG] Task {os.path.basename(task_file)}: {debug_info}', file=sys.stderr)
		if agent_output:
			print(f'[DEBUG] Agent output preview: {agent_output[:200]}...', file=sys.stderr)
		else:
			print('[DEBUG] Agent produced no output!', file=sys.stderr)

		criteria = '\n- '.join(judge_context)
		judge_prompt = f"""
You are a evaluator of a browser agent task inside a ci/cd pipeline. Here was the agent's task:
{task}

Here is the agent's output:
{agent_output if agent_output else '[No output provided]'}

Debug info: {debug_info}

Criteria for success:
- {criteria}

Reply in JSON with keys: success (true/false), explanation (string).
If the agent provided no output, explain what might have gone wrong.
"""
		structured_llm = judge_llm.with_structured_output(JudgeResponse)
		judge_response: JudgeResponse = await structured_llm.ainvoke(judge_prompt)  # type: ignore[assignment]

		result = {
			'file': os.path.basename(task_file),
			'success': judge_response.success,
			'explanation': judge_response.explanation,
		}

		# Clean up session before returning
		await session.stop()

		return result

	except Exception as e:
		# Ensure session cleanup even on error
		try:
			await session.stop()
		except Exception:
			pass

		return {'file': os.path.basename(task_file), 'success': False, 'explanation': f'Task failed with error: {str(e)}'}


async def run_task_subprocess(task_file, semaphore):
	"""Run a task in a separate subprocess"""
	async with semaphore:
		try:
			# Set environment to reduce noise in subprocess
			env = os.environ.copy()
			env['PYTHONPATH'] = os.pathsep.join(sys.path)

			proc = await asyncio.create_subprocess_exec(
				sys.executable,
				'-u',
				__file__,
				'--task',
				task_file,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
				env=env,
			)
			# THIS WAS BLINDING ME AND I HAVE PROBLEMS WITH THE GitHub ACTIONS EXECUTION ...
			# stdout, stderr = await proc.communicate()
			stdout_buffer = []
			stderr_buffer = []
			proc_name = os.path.basename(task_file)

			# Create tasks to read stdout and stderr concurrently to avoid deadlocks
			stdout_task = asyncio.create_task(_stream_reader(proc.stdout, stdout_buffer, sys.stdout))
			stderr_task = asyncio.create_task(_stream_reader(proc.stderr, stderr_buffer, sys.stderr))

			# Wait for the process to finish and the readers to drain the pipes
			await proc.wait()
			await asyncio.gather(stdout_task, stderr_task)
			stdout, stderr = b"".join(stdout_buffer), b"".join(stderr_buffer)

			if proc.returncode == 0:
				try:
					# Parse JSON result from subprocess
					stdout_text = stdout.decode().strip()
					stderr_text = stderr.decode().strip()

					# Display subprocess debug logs
					# if stderr_text:
					# 	print(f'[SUBPROCESS {os.path.basename(task_file)}] Debug output:')
					# 	for line in stderr_text.split('\n'):
					# 		if line.strip():
					# 			print(f'  {line}')

					# Find the JSON line (should be the last line that starts with {)
					lines = stdout_text.split('\n')
					json_line = None
					for line in reversed(lines):
						line = line.strip()
						if line.startswith('{') and line.endswith('}'):
							json_line = line
							break

					if json_line:
						result = json.loads(json_line)
						print(f'[PARENT] Task {os.path.basename(task_file)} completed: {result["success"]}')
					else:
						raise ValueError(f'No JSON found in output: {stdout_text}')

				except (json.JSONDecodeError, ValueError) as e:
					result = {
						'file': os.path.basename(task_file),
						'success': False,
						'explanation': f'Failed to parse subprocess result: {str(e)[:100]}',
					}
					print(f'[PARENT] Task {os.path.basename(task_file)} failed to parse: {str(e)}')
					print(f'[PARENT] Full stdout was: {stdout.decode()[:500]}')
			else:
				stderr_text = stderr.decode().strip()
				result = {
					'file': os.path.basename(task_file),
					'success': False,
					'explanation': f'Subprocess failed (code {proc.returncode}): {stderr_text[:200]}',
				}
				print(f'[PARENT] Task {os.path.basename(task_file)} subprocess failed with code {proc.returncode}')
				if stderr_text:
					print(f'[PARENT] stderr: {stderr_text[:1000]}')
				stdout_text = stdout.decode().strip()
				if stdout_text:
					print(f'[PARENT] stdout: {stdout_text[:1000]}')
		except Exception as e:
			result = {
				'file': os.path.basename(task_file),
				'success': False,
				'explanation': f'Failed to start subprocess: {str(e)}',
			}
			print(f'[PARENT] Failed to start subprocess for {os.path.basename(task_file)}: {str(e)}')

		return result


async def main():
	"""Run all tasks in parallel using subprocesses"""
	# semaphore = asyncio.Semaphore(MAX_PARALLEL)

	print(f'Found task files: {TASK_FILES}')

	if not TASK_FILES:
		print('No task files found!')
		return 0, 0

	# TODO: I'm a poor mouse, I can't afford this. I was hitting the 15 RPM limit for gemini-2.0-flash ...
	# Run all tasks in parallel subprocesses:
	# tasks = [run_task_subprocess(task_file, semaphore) for task_file in TASK_FILES]
	# results = await asyncio.gather(*tasks)

	# Run all tasks sequentially
	results = []
	TIMEOUT = 120
	for i, task_file in enumerate(TASK_FILES):
		try:
			# Use a semaphore of 1 for sequential execution, with 120s timeout because this gets stuck from time to time and I removed all the internal timeouts
			result = await asyncio.wait_for(run_task_subprocess(task_file, asyncio.Semaphore(1)), TIMEOUT)
			results.append(result)
		except asyncio.TimeoutError:
			results.append({'file': os.path.basename(task_file), 'success': False, 'explanation': f'Task timed out after {TIMEOUT} seconds'})
		if i != len(TASK_FILES) - 1:
			SECONDS_BETWEEN_EXECUTIONS = 30 # Again: poor mouse case ...
			print(f'[MAIN]  Waiting additional [{SECONDS_BETWEEN_EXECUTIONS}] seconds between tasks to avoid 429 errors ...')
			await asyncio.sleep(30)  

	passed = sum(1 for r in results if r['success'])
	total = len(results)

	print('\n' + '=' * 60)
	print(f'{"RESULTS":^60}\n')

	# Prepare table data
	headers = ['Task', 'Success', 'Reason']
	rows = []
	for r in results:
		status = '✅' if r['success'] else '❌'
		rows.append([r['file'], status, r['explanation']])

	# Calculate column widths
	col_widths = [max(len(str(row[i])) for row in ([headers] + rows)) for i in range(3)]

	# Print header
	header_row = ' | '.join(headers[i].ljust(col_widths[i]) for i in range(3))
	print(header_row)
	print('-+-'.join('-' * w for w in col_widths))

	# Print rows
	for row in rows:
		print(' | '.join(str(row[i]).ljust(col_widths[i]) for i in range(3)))

	print('\n' + '=' * 60)
	print(f'\n{"SCORE":^60}')
	print(f'\n{"=" * 60}\n')
	print(f'\n{"*" * 10}  {passed}/{total} PASSED  {"*" * 10}\n')
	print('=' * 60 + '\n')

	# Output results for GitHub Actions
	print(f'PASSED={passed}')
	print(f'TOTAL={total}')

	# Output detailed results as JSON for GitHub Actions
	detailed_results = []
	for r in results:
		detailed_results.append({'task': r['file'].replace('.yaml', ''), 'success': r['success'], 'reason': r['explanation']})

	print('DETAILED_RESULTS=' + json.dumps(detailed_results))

	return passed, total


if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--task', type=str, help='Path to a single task YAML file (for subprocess mode)')
	args = parser.parse_args()

	if args.task:
		# Subprocess mode: run a single task and output ONLY JSON
		try:
			result = asyncio.run(run_single_task(args.task))
			# Output ONLY the JSON result, nothing else
			print(json.dumps(result))
		except Exception as e:
			# Even on critical failure, output valid JSON
			error_result = {
				'file': os.path.basename(args.task),
				'success': False,
				'explanation': f'Critical subprocess error: {str(e)}',
			}
			print(json.dumps(error_result))
	else:
		# Parent process mode: run all tasks in parallel subprocesses
		passed, total = asyncio.run(main())
		# Results already printed by main() function
