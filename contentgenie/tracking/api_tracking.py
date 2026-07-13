import json

from contentgenie.database.content_data_manager import ContentDataManager
from contentgenie.gpt import gpt_utils


class APITracker:
    def __init__(self):
        self.datastore = None
        self.initiateAPITracking()

    def setDataManager(self, contentManager: ContentDataManager):
        if not contentManager:
            raise Exception("contentManager is null")
        self.datastore = contentManager

    def llmWrapper(self, gptFunc):
        def wrapper(*args, **kwargs):
            result = gptFunc(*args, **kwargs)
            prompt = kwargs.get('prompt') or kwargs.get('conversation') or args[0]
            prompt = json.dumps(prompt)
            if self.datastore and result:
                tokensUsed = gpt_utils.num_tokens_from_messages([prompt, result])
                self.datastore.save('api_llm', tokensUsed, add=True)
            return result

        return wrapper

    def wrap_llm(self):
        func_name = "llm_completion"
        module = __import__("gpt_utils", fromlist=["llm_completion"])
        func = getattr(module, func_name)
        wrapped_func = self.llmWrapper(func)
        setattr(module, func_name, wrapped_func)

    def initiateAPITracking(self):
        self.wrap_llm()
