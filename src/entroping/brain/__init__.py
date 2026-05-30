"""AI adapter boundary for LiteLLM-backed Architect roles."""

from entroping.brain.litellm_client import (
    BrainProviderError,
    BrainProviderUnavailableError,
    LiteLLMClient,
    LiteLLMCompletionResult,
    LiteLLMUsage,
)
from entroping.brain.persona_loader import AgentPersona, PersonaLoadError, load_agent_persona
from entroping.brain.prompt_builder import (
    ArchitectPromptPackage,
    PromptBuildError,
    PromptMessage,
    build_architect_prompt_package,
)

__all__ = [
    "AgentPersona",
    "ArchitectPromptPackage",
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
]
