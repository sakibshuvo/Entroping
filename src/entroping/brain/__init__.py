"""AI adapter boundary for LiteLLM-backed Architect roles."""

from entroping.brain.architect_build import ArchitectPromptBuildResult, run_architect_prompt_build
from entroping.brain.architect_writer import ArchitectWriteError, write_architect_edits
from entroping.brain.litellm_client import (
    BrainProviderError,
    BrainProviderUnavailableError,
    LiteLLMClient,
    LiteLLMCompletionResult,
    LiteLLMUsage,
)
from entroping.brain.output_parser import ArchitectOutputParseError, parse_architect_edit_set
from entroping.brain.persona_loader import AgentPersona, PersonaLoadError, load_agent_persona
from entroping.brain.prompt_builder import (
    ArchitectPromptPackage,
    PromptBuildError,
    PromptMessage,
    build_architect_prompt_package,
)

__all__ = [
    "AgentPersona",
    "ArchitectOutputParseError",
    "ArchitectPromptBuildResult",
    "ArchitectPromptPackage",
    "ArchitectWriteError",
    "BrainProviderError",
    "BrainProviderUnavailableError",
    "LiteLLMClient",
    "LiteLLMCompletionResult",
    "LiteLLMUsage",
    "PersonaLoadError",
    "PromptBuildError",
    "PromptMessage",
    "build_architect_prompt_package",
    "load_agent_persona",
    "parse_architect_edit_set",
    "run_architect_prompt_build",
    "write_architect_edits",
]
