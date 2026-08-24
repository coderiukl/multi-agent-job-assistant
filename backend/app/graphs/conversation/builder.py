from langgraph.graph import START, END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graphs.conversation.nodes import ConversationNodes
from app.graphs.conversation.routing import route_after_intent, ConversationRoute
from app.graphs.conversation.state import ConversationState

def build_conversation_graph(nodes: ConversationNodes) -> CompiledStateGraph:
    graph = StateGraph(ConversationState)

    graph.add_node("resolve_context", nodes.resolve_context)
    graph.add_node("analyzer_intent", nodes.analyze_intent)
    graph.add_node("clarification", nodes.respond_clarification)
    graph.add_node("small_talk", nodes.respond_small_talk)
    graph.add_node("out_of_scope", nodes.respond_out_out_scope)
    graph.add_node("general_question", nodes.respond_general_question)
    graph.add_node("business_task", nodes.dispatch_business_task)

    graph.add_edge(START, "resolve_context")
    graph.add_edge("resolve_context", "analyzer_intent")

    graph.add_conditional_edges(
        "analyzer_intent", 
        route_after_intent, 
        {
            ConversationRoute.CLARIFICATION: "clarification",
            ConversationRoute.SMALL_TALK: "small_talk",
            ConversationRoute.OUT_OF_SCOPE: "out_of_scope",
            ConversationRoute.GENERAL_QUESTION: "general_question",
            ConversationRoute.CV_ANALYSIS: "business_task",
            ConversationRoute.JOB_SEARCH: "business_task",
            ConversationRoute.JOB_MATCHING: "business_task",
            ConversationRoute.CAREER_ADVICE: "business_task",
            ConversationRoute.COVER_LETTER: "business_task",
        },
    )

    graph.add_edge("clarification", END)
    graph.add_edge("small_talk", END)
    graph.add_edge("out_of_scope", END)
    graph.add_edge("general_question", END)
    graph.add_edge("business_task", END)

    return graph.compile()
