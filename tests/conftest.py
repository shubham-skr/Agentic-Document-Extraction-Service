import sys, types
try:
    import openai  # noqa: F401
except ImportError:
    stub=types.ModuleType('openai')
    class AsyncOpenAI:
        def __init__(self,*a,**k): raise RuntimeError('OpenAI client is not installed; install requirements.txt')
    stub.AsyncOpenAI=AsyncOpenAI
    sys.modules['openai']=stub
