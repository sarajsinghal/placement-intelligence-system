"""Integration seams. Providers require real credentials/configuration."""
class ModelAdapter:
    def summarize(self, text: str) -> str: raise NotImplementedError("Configure an approved model provider and credentials first.")
class GoogleFormsAdapter:
    def connect(self): raise NotImplementedError("Google OAuth and Forms/Sheets API setup is required.")
