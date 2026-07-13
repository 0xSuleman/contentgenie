import numpy as np

from contentgenie.database.content_database import ContentDatabase

db = ContentDatabase()
all_content = []

llm_array = [short.get('api_llm') for short in all_content]
llm_array = [value for value in llm_array if value is not None]

if llm_array:
    print("LLM:")
    print("- Average tokens:", np.mean(llm_array))
    print("- Max tokens:", max(llm_array))
else:
    print("No LLM usage data available.")
