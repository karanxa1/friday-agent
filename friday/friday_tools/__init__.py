"""Tool families ported from the reference agent.

Each module registers a toolset:
  files  -> workspace file operations (the reference file_tools)
  web    -> fetch_url / download_file (the reference web_tools, with url_safety)
  todo   -> task list (the reference todo_tool)
  recall -> memory + activity search (the reference session_search/memory_tool)
  system -> run shell commands, glob, and grep within the file root
"""
