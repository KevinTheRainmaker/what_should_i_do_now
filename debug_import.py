try:
    print("Testing imports...")
    
    from app.nodes.context_node import initialize_context
    print("✅ context_node")
    
    from app.nodes.query_node import generate_search_queries
    print("✅ query_node")
    
    from app.nodes.search_node import search_and_normalize
    print("✅ search_node")
    
    from app.nodes.classifier_node import classify_time_fitness
    print("✅ classifier_node")
    
    from app.nodes.ranker_node import rank_activities
    print("✅ ranker_node")
    
    from app.nodes.llm_evaluator_node import llm_evaluate_and_select
    print("✅ llm_evaluator_node")
    
    from app.nodes.fallback_node import generate_fallback
    print("✅ fallback_node")
    
    from app.graph.companion_graph import companion_graph
    print("✅ companion_graph")
    
    print("All imports successful!")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
