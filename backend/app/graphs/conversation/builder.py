from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.conversation.nodes import ConversationNodes
from app.graphs.conversation.routing import (
    IntentGateRoute,
    WorkflowRoute,
    HumanReviewRoute,
    route_after_analysis,
    route_next_workflow_step,
    route_workflow_start,
    route_after_human_review,
)
from app.graphs.conversation.state import ConversationState
from app.schemas.conversation import ConversationRoute


def build_conversation_graph(
    nodes: ConversationNodes,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:

    graph = StateGraph(ConversationState)

    # Core conversations nodes
    graph.add_node("prepare_turn", nodes.prepare_turn)
    graph.add_node("record_assistant_message", nodes.record_assistant_message)
    graph.add_node("resolve_context", nodes.resolve_context)
    graph.add_node("analyze_intent", nodes.analyze_intent)

    # Workflow orchestration nodes
    graph.add_node("plan_workflow", nodes.create_workflow)
    graph.add_node("workflow_job_search", nodes.execute_workflow_job_search)
    graph.add_node("workflow_job_matching", nodes.execute_workflow_job_matching)
    graph.add_node("workflow_career_advice", nodes.execute_workflow_career_advice)
    graph.add_node("workflow_cv_analysis", nodes.execute_workflow_cv_analysis)
    graph.add_node("workflow_cover_letter", nodes.execute_workflow_cover_letter)
    graph.add_node("workflow_response", nodes.build_workflow_response)

    # Existing single-agent nodes
    graph.add_node("clarification", nodes.respond_clarification)
    graph.add_node("small_talk", nodes.respond_small_talk)
    graph.add_node("out_of_scope", nodes.respond_out_out_scope)
    graph.add_node("general_question", nodes.respond_general_question)
    graph.add_node("cv_analysis", nodes.execute_cv_analysis)
    graph.add_node("career_advice", nodes.execute_career_advice)
    graph.add_node("cover_letter", nodes.execute_cover_letter)
    graph.add_node("job_search", nodes.execute_job_search)
    graph.add_node("job_matching", nodes.execute_job_matching)

    # Human-in-the-loop
    graph.add_node("human_review", nodes.review_before_cover_letter)
    graph.add_node("human_review_rejected", nodes.respond_human_review_rejected)

    graph.add_edge(START, "prepare_turn")
    graph.add_edge("prepare_turn", "resolve_context")
    graph.add_edge("resolve_context", "analyze_intent")

    graph.add_conditional_edges(
        "analyze_intent",
        route_after_analysis,
        {
            IntentGateRoute.CLARIFICATION: "clarification",
            IntentGateRoute.PLAN_WORKFLOW: "plan_workflow",
        },
    )

    # Single Agent Routes
    single_agent_routes = {
        ConversationRoute.CLARIFICATION: "clarification",
        ConversationRoute.SMALL_TALK: "small_talk",
        ConversationRoute.OUT_OF_SCOPE: "out_of_scope",
        ConversationRoute.GENERAL_QUESTION: "general_question",
        ConversationRoute.CV_ANALYSIS: "cv_analysis",
        ConversationRoute.JOB_SEARCH: "job_search",
        ConversationRoute.JOB_MATCHING: "job_matching",
        ConversationRoute.CAREER_ADVICE: "career_advice",
        ConversationRoute.COVER_LETTER: "human_review",
    }

    # Multi-agent workflow
    workflow_step_routes = {
        WorkflowRoute.JOB_SEARCH: "workflow_job_search",
        WorkflowRoute.JOB_MATCHING: "workflow_job_matching",
        WorkflowRoute.CAREER_ADVICE: "workflow_career_advice",
        WorkflowRoute.CV_ANALYSIS: "workflow_cv_analysis",
        WorkflowRoute.COVER_LETTER: "human_review",
        WorkflowRoute.END: "workflow_response",
    }

    workflow_start_routes = {
        **single_agent_routes,
        **{
            node_name: node_name
            for node_name in workflow_step_routes.values()
        }
    }

    graph.add_conditional_edges(
        "plan_workflow",
        route_workflow_start,
        workflow_start_routes,    
    )

    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            HumanReviewRoute.WORKFLOW_COVER_LETTER: "workflow_cover_letter",
            HumanReviewRoute.SINGLE_COVER_LETTER: "cover_letter",
            HumanReviewRoute.REJECTED: "human_review_rejected",
        },
    )

    workflow_nodes = [
        "workflow_job_search",
        "workflow_job_matching",
        "workflow_career_advice",
        "workflow_cv_analysis",
        "workflow_cover_letter",
    ]

    for node_name in workflow_nodes:
        graph.add_conditional_edges(
            node_name,
            route_next_workflow_step,
            workflow_step_routes
        )

    terminal_nodes = (
        "workflow_response",
        "clarification",
        "small_talk",
        "out_of_scope",
        "general_question",
        "cv_analysis",
        "job_search",
        "job_matching",
        "career_advice",
        "cover_letter",
        "human_review_rejected",
    )

    for node_name in terminal_nodes:
        graph.add_edge(
            node_name,
            "record_assistant_message",
        )

    graph.add_edge("record_assistant_message", END)

    return graph.compile(checkpointer=checkpointer)
