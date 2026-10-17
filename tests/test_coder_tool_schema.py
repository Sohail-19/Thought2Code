from langchain_core.utils.function_calling import convert_to_openai_tool

from agent.prompts import coder_system_prompt
from agent.tools import list_generated_files


def test_file_listing_tool_has_explicit_groq_compatible_schema():
    schema = convert_to_openai_tool(list_generated_files)

    assert list_generated_files.name == "list_generated_files"
    assert schema["function"]["name"] == "list_generated_files"
    assert schema["function"]["parameters"] == {
        "type": "object",
        "properties": {"directory": {"type": "string", "default": "."}},
    }


def test_coder_prompt_uses_exact_file_listing_tool_name():
    prompt = coder_system_prompt()

    assert 'list_generated_files with {"directory": "."}' in prompt
    assert 'do not call a generic tool named "list"' in prompt
