import libcst as cst
from libcst import matchers as m


class ChatGoogleTransformer(cst.CSTTransformer):

  def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
    new_body = []
    for stmt in updated_node.body:
      # Insert import logging after import json once
      if (
          isinstance(stmt, cst.SimpleStatementLine)
          and len(stmt.body) == 1
          and isinstance(stmt.body[0], cst.Import)
          and any(alias.name.value == "json" for alias in stmt.body[0].names)
      ):
        new_body.append(stmt)
        import_logging = cst.SimpleStatementLine(
          body=[cst.Import(names=[cst.ImportAlias(name=cst.Name("logging"))])]
        )
        new_body.append(import_logging)
        continue
      # Insert logger assignment before the target function definition once
      if (
          isinstance(stmt, cst.FunctionDef)
          and stmt.name.value == "_is_retryable_error"
      ):
        logger_assign = cst.parse_statement(
          "\nlogger = logging.getLogger(__name__)"
        )
        new_body.append(logger_assign)

      new_body.append(stmt)

    return updated_node.with_changes(body=new_body)

  def leave_SimpleStatementLine(self, original_node, updated_node):
    if (len(updated_node.body) == 1
        and m.matches(
          updated_node.body[0],
          m.Assign(
            targets=[m.AssignTarget(target=m.Name("delay"))],
            value=m.Call(func=m.Name("min")))
        )
    ):
      # possible saviour ...
      return cst.FlattenSentinel([
        updated_node,
        cst.parse_statement("error_msg = str(e)"),
        cst.parse_statement("prefix = f'❌ Invocation to LLM number {attempt} failed. Waiting for {delay} seconds before retrying:\\n '"),
        cst.parse_statement("logger.error(f'{prefix}{error_msg}')"),
      ])

    target_line = "parsed_data = json.loads(response.text)"
    expr_code = cst.Module([]).code_for_node(original_node.body[0]).strip()
    if expr_code.strip() == target_line.strip():
      return cst.FlattenSentinel([
        # I hate all this addtional manipulations needed with comments. They should be entities on their own ...
        cst.EmptyLine(comment=cst.Comment("# Parse the JSON text and validate with the Pydantic model")),
        cst.parse_statement("parsed_data = json.loads(repair_json(clean_response_before_parsing(response.text)))"),
      ])

    return updated_node

  NEW_FUNC_CODE = '''
def get_client(self) -> genai.Client:
    """
    Returns a genai.Client instance.

    Returns:
        genai.Client: An instance of the Google genai client.
    """
    # This was suggested to me by Perplexity and, empirically, it seems to reduce the number of 429 RESOURCE_EXHAUSTED errors.
    if not self.client:
        client_params = self._get_client_params()
        self.client = genai.Client(**client_params)
        
    return self.client
'''

  BEAUTIFUL_JSON_FIX = '''
def clean_response_before_parsing(response: str) -> str:
    # Cleans the raw LLM response string before attempting to parse it as JSON.
    # - Removes markdown code block fences (```json ... ```).
    # - Replaces Python-specific string escapes like \\\\' with a standard single quote.

    json_text = response.strip()
    if json_text.startswith('```json'):
        json_text = json_text[len('```json'): -len('```')].strip()
    elif json_text.startswith('```'):
        json_text = json_text[len('```'): -len('```')].strip()

    # The response might have escaped single quotes from python's repr, which are not valid in JSON
    json_text = json_text.replace("\\\\'", "'")
    return json_text

# --- Helper Functions for Readability ---
def is_char_escaped(s: str, index: int) -> bool:
    # Checks if the character at a given index in a string is escaped by a backslash.
    # Handles multiple preceding backslashes (e.g., "abc\\\\\\"def" -> '\\"' is escaped).
    if index == 0:
        return False

    num_backslashes = 0
    i = index - 1
    while i >= 0 and s[i] == '\\\\':
        num_backslashes += 1
        i -= 1

    # If the number of preceding backslashes is odd, the character is escaped.
    return num_backslashes % 2 == 1

def find_next_non_whitespace(text: str, start_index: int) -> int:
    # Finds the index of the next non-whitespace character from a starting position.
    for i in range(start_index, len(text)):
        if not text[i].isspace():
            return i
    return -1

def find_next_unescaped_char(text: str, char_to_find: str, start_index: int) -> int:
    # Finds the next occurrence of a character that is not escaped by a backslash.
    pos = text.find(char_to_find, start_index)
    while pos != -1:
        if not is_char_escaped(text, pos):
            return pos
        # It was escaped, so search again from the next character.
        pos = text.find(char_to_find, pos + 1)
    return -1

def repair_json(text: str) -> str:
    # Repairs a JSON-like string by finding and escaping string values.
    # This version uses a two-pass approach for clarity and correctness:
    # 1. First pass: Identify all string values that need repair.
    # 2. Second pass: Build the new string using the identified segments.

    repairs = []
    cursor = 0

    # Pass 1: Find all segments to repair.
    while cursor < len(text):
        # Find a key-value pair where the value is a string.
        key_start_pos = find_next_unescaped_char(text, '"', cursor)
        if key_start_pos == -1: break

        key_end_pos = find_next_unescaped_char(text, '"', key_start_pos + 1)
        if key_end_pos == -1: break

        colon_pos = find_next_non_whitespace(text, key_end_pos + 1)
        if colon_pos == -1 or text[colon_pos] != ':':
            cursor = key_start_pos + 1
            continue

        value_start_pos = find_next_non_whitespace(text, colon_pos + 1)
        if value_start_pos == -1 or text[value_start_pos] != '"':
            cursor = value_start_pos if value_start_pos != -1 else colon_pos + 1
            continue

        # Find the true end of the string value.
        content_start_pos = value_start_pos + 1
        search_pos = content_start_pos
        value_end_pos = -1

        while search_pos < len(text):
            potential_end_pos = find_next_unescaped_char(text, '"', search_pos)
            if potential_end_pos == -1: break

            char_after_quote_pos = find_next_non_whitespace(text, potential_end_pos + 1)
            if char_after_quote_pos != -1 and text[char_after_quote_pos] in ',}]':
                value_end_pos = potential_end_pos
                break
            else:
                search_pos = potential_end_pos + 1

        if value_end_pos != -1:
            # Found a segment. Store its start, end, and the escaped content.
            content = text[content_start_pos:value_end_pos]
            escaped_content = json.dumps(content)[1:-1]
            repairs.append((content_start_pos, value_end_pos, escaped_content))
            cursor = value_end_pos + 1
        else:
            # Malformed, could not find end. Skip past this key to avoid getting stuck.
            cursor = key_start_pos + 1

    # Pass 2: Build the new string from the original text and the repairs.
    if not repairs:
        return text

    output_parts = []
    last_pos = 0
    for start, end, replacement in repairs:
        output_parts.append(text[last_pos:start])
        output_parts.append(replacement)
        last_pos = end

    output_parts.append(text[last_pos:])

    return "".join(output_parts)
'''

  def leave_FunctionDef(self, original_node, updated_node):
    if updated_node.name.value == "_make_api_call":
      body = list(updated_node.body.body)
      insert_at = 0

      # Insert after docstring if present
      if (
          body
          and isinstance(body[0], cst.SimpleStatementLine)
          and isinstance(body[0].body[0], cst.Expr)
          and isinstance(body[0].body[0].value, cst.SimpleString)
      ):
        insert_at = 1

      # Use parse_statement for valid statements only:
      stmts = [
        cst.parse_statement("import asyncio"),
        cst.parse_statement("LLM_TIMEOUT_SECONDS = 20"),
      ]

      # Attach comment as leading comment on the assignment stmt
      stmts[1] = stmts[1].with_changes(
        leading_lines=[cst.EmptyLine(comment=cst.Comment("# Timeout for LLM API calls in seconds: Gemini is killing me and getting stuck forever ..."))]
      )

      for stmt in reversed(stmts):
        body.insert(insert_at, stmt)

      updated_node = updated_node.with_changes(body=updated_node.body.with_changes(body=body))

    if original_node.name.value == "get_client":
      new_func = cst.parse_module(self.NEW_FUNC_CODE)  # parse entire function as module, get first stmt (FunctionDef) => possible saviour
      return new_func

    if original_node.name.value == "ainvoke" and not original_node.decorators:
      # Identify the target line using a string match
      target_line = "async def _make_api_call():"

      new_body = []
      for stmt in updated_node.body.body:
        expr_code = cst.Module([]).code_for_node(stmt).strip()
        if (expr_code.startswith(target_line)):
          # Inserting BEAUTIFUL_JSON_FIX before 'target_line' ...
          new_stmts_module = cst.parse_module(self.BEAUTIFUL_JSON_FIX)
          new_body.append(new_stmts_module)

        new_body.append(stmt)

      return updated_node.with_changes(body=updated_node.body.with_changes(body=new_body))

    return updated_node

  # leave_Await is called after visiting the child of an await expression node => possible saviour
  def leave_Await(self, original_node, updated_node):
    # Get code string of the expression safely
    expr_code = cst.Module([]).code_for_node(updated_node.expression)

    if expr_code.startswith("self.get_client().aio.models.generate_content"):
      new_call = cst.parse_expression(
        f"asyncio.wait_for({expr_code}, timeout=LLM_TIMEOUT_SECONDS)"
      )
      return updated_node.with_changes(expression=new_call)

    return updated_node

  def leave_ClassDef(self, original_node, updated_node):
    if original_node.name.value == "ChatGoogle":
      target_line = "http_options: types.HttpOptions | types.HttpOptionsDict | None = None"

      new_stmts = [
        cst.EmptyLine(),
        cst.EmptyLine(comment=cst.Comment(
          "# This was suggested to me by Perplexity and, empirically, it seems to reduce the number of 429 RESOURCE_EXHAUSTED errors.")),
        cst.parse_statement("client: genai.Client | None = None\n"),
        cst.EmptyLine()
      ]

      old_body = list(updated_node.body.body)

      idx = None
      for i, stmt in enumerate(old_body):
        # Use Module([]).code_for_node(node)
        if cst.Module([]).code_for_node(stmt).strip() == target_line:
          idx = i
          break

      new_body = old_body[:idx + 1] + new_stmts + old_body[idx + 1:]

      return updated_node.with_changes(
        body=updated_node.body.with_changes(body=tuple(new_body))
      )

    return updated_node
