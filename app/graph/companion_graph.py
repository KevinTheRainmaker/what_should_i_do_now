from typing import Dict, Any
from langgraph.graph import StateGraph, END
from app.nodes.context_node import initialize_context
from app.nodes.query_node import generate_search_queries
from app.nodes.search_node import search_and_normalize
from app.nodes.travel_time_filter_node import calculate_travel_time_filter
from app.nodes.classifier_node import classify_time_fitness
from app.nodes.ranker_node import rank_activities
from app.nodes.llm_evaluator_node import llm_evaluate_and_select
from app.nodes.review_fetcher_node import fetch_and_summarize_reviews
from app.nodes.fallback_node import generate_fallback


def create_companion_graph():
    """Gap-time Companion Agent 그래프 생성"""
    
    # 그래프 생성 - 상태를 Dict[str, Any]로 사용
    workflow = StateGraph(Dict[str, Any])
    
    # 노드 추가
    workflow.add_node("initialize_context", initialize_context)
    workflow.add_node("generate_queries", generate_search_queries)
    workflow.add_node("search_and_normalize", search_and_normalize)
    workflow.add_node("filter_by_travel_time", calculate_travel_time_filter)
    workflow.add_node("classify_time", classify_time_fitness)
    workflow.add_node("rank_activities", rank_activities)
    workflow.add_node("llm_evaluate", llm_evaluate_and_select)
    workflow.add_node("fetch_reviews", fetch_and_summarize_reviews)
    workflow.add_node("generate_fallback", generate_fallback)
    
    # 엣지 정의 (워크플로우)
    workflow.set_entry_point("initialize_context")
    
    workflow.add_edge("initialize_context", "generate_queries")
    workflow.add_edge("generate_queries", "search_and_normalize")
    workflow.add_edge("search_and_normalize", "filter_by_travel_time")
    workflow.add_edge("filter_by_travel_time", "classify_time")
    workflow.add_edge("classify_time", "rank_activities")
    workflow.add_edge("rank_activities", "llm_evaluate")
    workflow.add_edge("llm_evaluate", "fetch_reviews")
    workflow.add_edge("fetch_reviews", "generate_fallback")
    workflow.add_edge("generate_fallback", END)
    
    # 컴파일
    graph = workflow.compile()
    
    return graph


def should_use_fallback(state: Dict[str, Any]) -> str:
    """폴백 사용 여부 결정"""
    ranked_items = state.get("ranked_items", [])
    
    if len(ranked_items) < 4:
        return "generate_fallback"
    else:
        return END


def create_advanced_companion_graph():
    """조건부 라우팅을 포함한 고급 그래프"""
    
    workflow = StateGraph(Dict[str, Any])
    
    # 노드 추가
    workflow.add_node("initialize_context", initialize_context)
    workflow.add_node("generate_queries", generate_search_queries)
    workflow.add_node("search_and_normalize", search_and_normalize)
    workflow.add_node("classify_time", classify_time_fitness)
    workflow.add_node("rank_activities", rank_activities)
    workflow.add_node("generate_fallback", generate_fallback)
    
    # 시작점
    workflow.set_entry_point("initialize_context")
    
    # 엣지 정의
    workflow.add_edge("initialize_context", "generate_queries")
    workflow.add_edge("generate_queries", "search_and_normalize")
    workflow.add_edge("search_and_normalize", "classify_time")
    workflow.add_edge("classify_time", "rank_activities")
    
    # 조건부 엣지 - 결과가 부족하면 폴백 사용
    workflow.add_conditional_edges(
        "rank_activities",
        should_use_fallback,
        {
            "generate_fallback": "generate_fallback",
            END: END
        }
    )
    
    workflow.add_edge("generate_fallback", END)
    
    return workflow.compile()


# 기본 그래프 인스턴스 생성
companion_graph = create_companion_graph()
