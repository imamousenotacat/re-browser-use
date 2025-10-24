import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider
from libcst import RemovalSentinel
from textwrap import dedent

NEW_DOCSTRING = (
  "Runs all agent tasks in parallel SEQUENTIALLY I'M A POOR MOUSE (up to 10 at a time) using separate subprocesses.\n"
  "Each task gets its own Python process, preventing browser session interference.\n"
  "Does not fail on partial failures (always exits 0)."
)

NEW_IMPORTS = [
  "import argparse",
  "import asyncio",
  "import glob",
  "import json",
  "import os",
  "import sys",
  "",
  "import datetime",
  "",
  "import anyio",
  "import yaml",
  "from pydantic import BaseModel",
  "",
  "from browser_use.agent.views import AgentHistoryList",
  "from tests.utils_for_tests import create_llm, create_stealth_browser_session, create_stealth_agent",
  "from browser_use.llm.messages import UserMessage"
]

HEADLESS_VAR = "HEADLESS_EVALUATION = os.environ.get('HEADLESS_EVALUATION', 'True').lower() == 'true'"
STREAM_READER = '''
async def _stream_reader(stream, buffer, print_stream):
    """Reads from a stream, buffers the output, and prints it in real-time."""
    while True:
        line = await stream.readline()
        if not line:
            break
        buffer.append(line)
        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-4]
        print(f"[{timestamp}] {line.decode(errors='ignore').strip()}", file=print_stream, flush=True)
'''


class EvaluateTaskTransformer(cst.CSTTransformer):

  METADATA_DEPENDENCIES = (PositionProvider,)

  def __init__(self):
    super().__init__()
    self.function_stack = []

  def visit_FunctionDef(self, node):
    self.function_stack.append(node.name.value)

  results_async_replacing_code = '''
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
'''

  def leave_FunctionDef(self, original_node, updated_node):
    self.function_stack.pop()

    new_body = []
    for stmt in updated_node.body.body:
      if m.matches( # results = await asyncio.gather(*tasks)
          stmt,
          m.SimpleStatementLine(
            body=[
              m.Assign(
                targets=[m.AssignTarget(target=m.Name("results"))],
                value=m.Await(
                  m.Call(
                    func=m.Attribute(
                      value=m.Name("asyncio"),
                      attr=m.Name("gather")
                    ),
                    args=[m.Arg(star="*", value=m.Name("tasks"))]
                  )
                ),
              )
            ]
          )
      ):
        # Parse and fix leading comments => possible saviour
        replacement_body = self._parse_and_fix_leading_comments(self.results_async_replacing_code)
        new_body.extend(replacement_body)
      else:
        new_body.append(stmt)

    return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

  def leave_Module(self, original_node, updated_node):
    # 1. Replace docstring
    new_docstring_node = cst.SimpleStatementLine(
      body=[cst.Expr(value=cst.SimpleString('"""' + NEW_DOCSTRING + '"""'))]
    )
    # 2. Replace imports
    new_import_nodes = []
    for line in NEW_IMPORTS:
      if line.strip() == "":
        new_import_nodes.append(cst.EmptyLine())
      else:
        new_import_nodes.append(cst.parse_statement(line))
    # 3. Find start of code after docstring/imports
    body = list(updated_node.body)
    idx = 0
    # Skip docstring if present
    if (
        body
        and isinstance(body[0], cst.SimpleStatementLine)
        and body[0].body
        and isinstance(body[0].body[0], cst.Expr)
        and isinstance(body[0].body[0].value, cst.SimpleString)
    ):
      idx = 1
    # Skip imports
    while (
        idx < len(body)
        and (
            isinstance(body[idx], cst.SimpleStatementLine)
            and (
                any(
                  isinstance(stmt, (cst.Import, cst.ImportFrom))
                  for stmt in body[idx].body
                )
                or all(isinstance(stmt, cst.Pass) for stmt in body[idx].body)
            )
            or isinstance(body[idx], cst.EmptyLine)
        )
    ):
      idx += 1

    # 4. Find TASK_FILES assignment
    insert_idx = None
    for i in range(idx, len(body)):
      stmt = body[i]
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and stmt.body
          and isinstance(stmt.body[0], cst.Assign)
          and isinstance(stmt.body[0].targets[0].target, cst.Name)
          and stmt.body[0].targets[0].target.value == "TASK_FILES"
      ):
        insert_idx = i + 1
        break

    # 5. Build new nodes for HEADLESS_EVALUATION and _stream_reader
    headless_node = cst.parse_statement(HEADLESS_VAR)
    stream_reader_node = cst.parse_statement(STREAM_READER)

    # 6. Insert new nodes after TASK_FILES
    if insert_idx is not None:
      new_body = (
          [new_docstring_node]
          + new_import_nodes
          + body[idx:insert_idx]
          + [headless_node, stream_reader_node]
          + body[insert_idx:]
      )
    else:
      # fallback: insert after imports
      new_body = (
          [new_docstring_node]
          + new_import_nodes
          + [headless_node, stream_reader_node]
          + body[idx:]
      )

    return updated_node.with_changes(body=new_body)

  def leave_Expr(self, original_node, updated_node):
    value = original_node.value
    # Removes logging.getLogger().setLevel(logging.CRITICAL) and the comment
    if (
        isinstance(value, cst.Call)
        and isinstance(value.func, cst.Attribute)
        and value.func.attr.value == "setLevel"
        and isinstance(value.func.value, cst.Call)
        and isinstance(value.func.value.func, cst.Attribute)
        and value.func.value.func.attr.value == "getLogger"
        and len(value.func.value.args) == 0
    ):
      return cst.RemoveFromParent()

    return updated_node

  # Removes for logger_name in ['browser_use', 'telemetry', 'message_manager']:
  def leave_For(self, original_node, updated_node):
    if (
        isinstance(original_node.target, cst.Name)
        and original_node.target.value == "logger_name"
        and isinstance(original_node.iter, cst.List)
        and all(
      isinstance(elt.value, cst.SimpleString)
      for elt in original_node.iter.elements
    )
    ):
      return cst.RemoveFromParent()

    return updated_node

  # using my function 'create_llm()' to create the LLMs
  def leave_Assign(self, original_node, updated_node):
    # Replace right side of agent_llm and judge_llm assignments
    if (
        len(original_node.targets) == 1
        and isinstance(original_node.targets[0].target, cst.Name)
        and original_node.targets[0].target.value in ("agent_llm", "judge_llm")
        and isinstance(original_node.value, cst.Call)
        and isinstance(original_node.value.func, cst.Name)
    ):
      return updated_node.with_changes(
        value=cst.Call(func=cst.Name("create_llm"), args=[])
      )

    # Replace right side of agent assignment
    if (  # Check if the assignment is to "agent"
        len(original_node.targets) == 1 and
        isinstance(original_node.targets[0].target, cst.Name) and
        original_node.targets[0].target.value == "agent"
    ):
      # Parse the new right side using cst.parse_statement
      new_right = cst.parse_statement(
        "agent = create_stealth_agent(task=task, llm=agent_llm, browser_session=session)"
      ).body[0].value  # .body returns a list of SimpleStatementLine, .value is the Assign node's value

      # Replace the value (right side) of the assignment
      return updated_node.with_changes(value=new_right)

    return updated_node

  # Replace profile = BrowserProfile(...) with playwright = await async_patchright().start()
  def leave_SimpleStatementLine(self, original_node, updated_node):
    # Remove the line if it matches profile = BrowserProfile(...)
    if (
        len(original_node.body) == 1
        and isinstance(original_node.body[0], cst.Assign)
        and isinstance(original_node.body[0].value, cst.Call)
        and isinstance(original_node.body[0].value.func, cst.Name)
        and original_node.body[0].value.func.value == "BrowserProfile"
    ):
      return RemovalSentinel.REMOVE

    # Replace the line if it matches session = BrowserSession(browser_profile=profile)
    if (
        len(original_node.body) == 1
        and isinstance(original_node.body[0], cst.Assign)
        and isinstance(original_node.body[0].value, cst.Call)
        and isinstance(original_node.body[0].value.func, cst.Name)
        and original_node.body[0].value.func.value == "BrowserSession"
    ):
      return cst.parse_statement("session = create_stealth_browser_session(headless=HEADLESS_EVALUATION)")

    # Match: semaphore = asyncio.Semaphore(MAX_PARALLEL)
    if m.matches(
        updated_node,
        m.SimpleStatementLine(
          body=[
            m.Assign(
              targets=[m.AssignTarget(target=m.Name("semaphore"))],
              value=m.Call(
                func=m.Attribute(
                  value=m.Name("asyncio"),
                  attr=m.Name("Semaphore")
                ),
                args=[m.Arg(value=m.Name("MAX_PARALLEL"))]
              ),
            )
          ]
        )
    ):
      return cst.SimpleStatementLine(
        [cst.Pass()],
        leading_lines=[
          cst.EmptyLine(comment=cst.Comment("# semaphore = asyncio.Semaphore(MAX_PARALLEL) (commented out by transformer)"))
        ]
      )

    # Match: tasks = [run_task_subprocess(task_file, semaphore) for task_file in TASK_FILES]
    if m.matches(
        updated_node,
        m.SimpleStatementLine(
          body=[
            m.Assign(
              targets=[m.AssignTarget(target=m.Name("tasks"))],
              value=m.ListComp(
                elt=m.Call(
                  func=m.Name("run_task_subprocess"),
                  args=[
                    m.Arg(value=m.Name("task_file")),
                    m.Arg(value=m.Name("semaphore"))
                  ]
                ),
                for_in=m.CompFor(
                  target=m.Name("task_file"),
                  iter=m.Name("TASK_FILES")
                )
              )
            )
          ]
        )
    ):
      return cst.SimpleStatementLine(
        [cst.Pass()],
        leading_lines=[
          cst.EmptyLine(),
          cst.EmptyLine(comment=cst.Comment("# TODO: I'm a poor mouse, I can't afford this. I was hitting the 15 RPM limit for gemini-2.0-flash ...")),
          cst.EmptyLine(comment=cst.Comment("# Run all tasks in parallel subprocesses: (block commented out by transformer)")),
          cst.EmptyLine(comment=cst.Comment("# tasks = [run_task_subprocess(task_file, semaphore) for task_file in TASK_FILES]")),
          cst.EmptyLine(comment=cst.Comment("# results = await asyncio.gather(*tasks)")),
        ]
      )

    # Match: warnings.filterwarnings('ignore') instead of removing we replace it with a comment
    if m.matches(
        updated_node,
        m.SimpleStatementLine(
          body=[
            m.Expr(
              value=m.Call(
                func=m.Attribute(
                  value=m.Name("warnings"),
                  attr=m.Name("filterwarnings")
                ),
                args=[m.Arg(value=m.SimpleString("'ignore'"))]
              )
            )
          ]
        )
    ):
      return cst.SimpleStatementLine(
        [cst.Pass()],
        leading_lines=[ # TODO: MOU14 WRITE A LITTLE UTILITY FUNCTION TO DO THIS CRAP
          cst.EmptyLine(),
          cst.EmptyLine(comment=cst.Comment("# Being blind it's a terrible thing :-( ... (commented out by transformer)")),
          cst.EmptyLine(comment=cst.Comment("# Suppress all logging in subprocess to avoid interfering with JSON output")),
          cst.EmptyLine(comment=cst.Comment("# logging.getLogger().setLevel(logging.CRITICAL)")),
          cst.EmptyLine(comment=cst.Comment("# for logger_name in ['browser_use', 'telemetry', 'message_manager']:")),
          cst.EmptyLine(comment=cst.Comment("#   logging.getLogger(logger_name).setLevel(logging.CRITICAL)")),
          cst.EmptyLine(comment=cst.Comment("# warnings.filterwarnings('ignore')")),
        ]
      )

    return updated_node

  proc_communicate_replacing_code = '''
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
  '''


  def leave_Try(self, original_node, updated_node):
    # => UNNEEDED start() CALL AND ERROR CHECKING: ALL THAT IS NEEDED TO HAVE A CLEAN AND PURE patchright STEALTH BROWSER IS ALREADY INITIALIZED ....
    #    There will be a call to BrowserSession.start() later in Agent.run but the bulk of the work has already been done here by create_stealth_browser_session
    if self.function_stack and self.function_stack[-1] == "run_single_task":
      # pos = self.get_metadata(PositionProvider, original_node)
      # func = self.function_stack[-1] if self.function_stack else None
      # print(f"Found at line: [{pos.start.line}], in function: {func}")

      for stmt in original_node.body.body:
        if isinstance(stmt, cst.SimpleStatementLine):
          for expr in stmt.body:
            if (# matching the simple expression "await session.start()"
                isinstance(expr, cst.Expr)
                and isinstance(expr.value, cst.Await)
                and isinstance(expr.value.expression, cst.Call)
                and isinstance(expr.value.expression.func, cst.Attribute)
                and isinstance(expr.value.expression.func.value, cst.Name)
                and expr.value.expression.func.value.value == "session"
                and expr.value.expression.func.attr.value == "start"
            ):
              # print(f"REMOVED at line: [{self.get_metadata(PositionProvider, original_node).start.line}], in function: run_single_task")
              # return cst.RemoveFromParent()
              return cst.SimpleStatementLine(
                [cst.Pass()],
                leading_lines=[
                  cst.EmptyLine(),
                  cst.EmptyLine(comment=cst.Comment(
                    "# => UNNEEDED start() CALL AND ERROR CHECKING: ALL THAT IS NEEDED TO HAVE A CLEAN AND PURE patchright STEALTH BROWSER IS ALREADY INITIALIZED ....")),
                  cst.EmptyLine(comment=cst.Comment(
                    "#    There will be a call to BrowserSession.start() later in Agent.run but the bulk of the work has already been done here by create_stealth_browser_session")),
                  cst.EmptyLine(comment=cst.Comment("#  Test if browser is working")),
                  cst.EmptyLine(comment=cst.Comment("#  try: # (try block removed by transformer)")),
                  cst.EmptyLine(comment=cst.Comment("#    await session.start()")),
                  cst.EmptyLine(comment=cst.Comment("#    page = await session.create_new_tab()")),
                  cst.EmptyLine(comment=cst.Comment("#    ...")),
                ]
              )

    # Replacing stdout, stderr = await proc.communicate() with a new buch of code ...
    if self.function_stack and self.function_stack[-1] == "run_task_subprocess":
      new_body = []
      for stmt in updated_node.body.body:
        # Yeah, I know is hellish code to identify "stdout, stderr = await proc.communicate()" , but it is what it is, you are parsing a syntax tree
        if m.matches(
            stmt,
            m.SimpleStatementLine(
              body=[
                m.Assign(
                  targets=[
                    m.AssignTarget(
                      target=m.Tuple(
                        elements=[
                          m.Element(value=m.Name("stdout")),
                          m.Element(value=m.Name("stderr")),
                        ]
                      )
                    )
                  ],
                  value=m.Await(
                    m.Call(
                      func=m.Attribute(
                        value=m.Name("proc"),
                        attr=m.Name("communicate")
                      )
                    )
                  )
                )
              ]
            )
        ):
          replacement_module_body = self._parse_and_fix_leading_comments(self.proc_communicate_replacing_code)
          new_body.extend(replacement_module_body)
        else:
          new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

  # Adding the new parameter -u to 'create_subprocess_exec' not to buffer std and stderr
  def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
    # Match the call to asyncio.create_subprocess_exec
    if m.matches(
        original_node.func,
        m.Attribute(
          value=m.Name("asyncio"),
          attr=m.Name("create_subprocess_exec")
        )
    ):
      # Extract the original arguments
      args = list(updated_node.args)

      # Check if '-u' is already present to avoid duplicates (optional)
      if any(
          isinstance(arg.value, cst.SimpleString) and arg.value.value == "'-u'" or arg.value.value == '"-u"'
          for arg in args
      ):
        return updated_node  # Already present, no change

      # Correct the string literal to normal ASCII hyphen-u
      new_arg = cst.Arg(value=cst.SimpleString("'-u'"))

      # Insert at position 1 (after sys.executable)
      args.insert(1, new_arg)

      # Return updated call with new args
      return updated_node.with_changes(args=args)

    return updated_node

  def leave_If(self, original_node, updated_node):
    # Only match if stderr_text and body contains a for loop
    if (
        m.matches(
          updated_node,
          m.If(
            test=m.Name("stderr_text"),
            body=m.IndentedBlock()
          )
        )
        and any(isinstance(stmt, cst.For) for stmt in updated_node.body.body)
    ):
      return cst.SimpleStatementLine(
        [cst.Pass()],
        leading_lines=[
          cst.EmptyLine(),
          cst.EmptyLine(comment=cst.Comment("# Display subprocess debug logs (block commented out by transformer)")),
          cst.EmptyLine(comment=cst.Comment("#  if stderr_text:")),
          cst.EmptyLine(comment=cst.Comment("#    print(f'[SUBPROCESS {os.path.basename(task_file)}] Debug output:')")),
          cst.EmptyLine(comment=cst.Comment("#    for line in stderr_text.split('\\n'):")),
          cst.EmptyLine(comment=cst.Comment("#      ...")),
        ]
      )

    return updated_node

  # The initial comments in a block of code were being ignored when used in a replacement operation
  def _parse_and_fix_leading_comments(self, replacement_code):
    replacement_module = cst.parse_module(dedent(replacement_code))
    if replacement_module.body:
      first_stmt = replacement_module.body[0]
      comments = []
      # LibCST >=0.4.0: module-level comments are in .header (older versions: not available)
      if hasattr(replacement_module, "header"):
        for leading_line in replacement_module.header:
          if isinstance(leading_line, cst.EmptyLine) and leading_line.comment:
            comments.append(leading_line)
      if comments:
        first_stmt = first_stmt.with_changes(
          leading_lines=comments + list(first_stmt.leading_lines)
        )
        new_body = (first_stmt,) + replacement_module.body[1:]
      else:
        new_body = replacement_module.body
    else:
      new_body = ()

    return new_body
