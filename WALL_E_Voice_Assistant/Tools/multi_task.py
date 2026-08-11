from livekit.agents import function_tool

@function_tool()
async def execute_multi_task(tasks: list[dict]) -> str:
    """
    Executes multiple tools sequentially as per user request.

    Args:
        tasks: A list of dictionaries, each containing:
            - 'tool_name': Name of the tool (string)
            - 'params': Dictionary of parameters for that tool

        Example:
        tasks = [
            {"tool_name": "get_weather", "params": {"location": "Surat"}},
            {"tool_name": "play_media", "params": {"media_path": "song.mp3"}},
            {"tool_name": "control_system_volume", "params": {"volume_level": 50}}
        ]

    Returns:
        A message indicating completion of all tasks.
    """
    results = []

    # Loop through each task sequentially
    for idx, task in enumerate(tasks, start=1):
        tool_name = task.get("tool_name")
        params = task.get("params", {})

        if not tool_name:
            results.append(f"⚠️ Task {idx}: 'tool_name' missing.")
            continue

        # Dynamically get the function
        tool_func = globals().get(tool_name)
        if not tool_func:
            results.append(f"⚠️ Task {idx}: Tool '{tool_name}' not found.")
            continue

        try:
            # Execute the tool and wait for completion before next
            result = await tool_func(**params)
            results.append(f"✅ Task {idx} ({tool_name}) executed: {result}")
        except Exception as e:
            results.append(f"❌ Task {idx} ({tool_name}) failed: {str(e)}")

    return "🔹 Multi-Task Execution Complete:\n" + "\n".join(results)
