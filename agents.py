# =============================================================================
# Add this endpoint to your agents.py file, BEFORE the main @router.get("") route
# =============================================================================

@router.get("/all")
async def list_all_agents(
    limit: Optional[int] = Query(None, ge=1, le=1000),
    status: Optional[str] = Query(None, pattern='^(online|offline|maintenance)$'),
    user: dict = Depends(verify_token)
):
    """
    List ALL agents without environment filtering.
    Used by Reports module to show all available agents regardless of user's environment access.
    Still requires authentication.
    """
    db = get_db()
    
    try:
        agents = db.list_agents_with_status(limit=limit, status=status)
    except AttributeError:
        agents = db.list_agents(limit=limit)
    
    # Update status for each agent via health check
    updated_agents = []
    for agent in agents:
        ssl_enabled = agent.get('ssl_enabled', SSL_ENABLED)
        is_healthy, _ = await check_agent_health(agent['host'], agent['port'], ssl_enabled)
        agent['status'] = 'online' if is_healthy else 'offline'
        updated_agents.append(agent)
    
    # Apply status filter if provided
    if status:
        updated_agents = [a for a in updated_agents if a.get('status') == status]
    
    logger.debug(f"Listed {len(updated_agents)} agents (unfiltered) for user {user.get('username', 'unknown')}")
    
    return {
        "agents": updated_agents,
        "count": len(updated_agents),
        "ssl_enabled": SSL_ENABLED
    }
