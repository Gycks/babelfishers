from pydantic import BaseModel, Field


class Culture(BaseModel):
    code: str
    name: str
    provider_codes: dict[str, str] = Field(default_factory=dict)

    def code_for(self, provider: str) -> str:
        """Return the provider-specific code, falling back to the canonical code.

        Args:
            provider (str): The name of the translation provider.

        Returns:
            (str): The provider-specific code if available, otherwise the canonical code.
        """
        return self.provider_codes.get(provider, self.code)
