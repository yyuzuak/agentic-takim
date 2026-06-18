"""Minimal LangGraph 'hello-graph' — durable execution kanıtı.

İki düğüm: plan → execute. Postgres checkpointer (AsyncPostgresSaver) sayesinde
çalışma yarıda kesilse bile (container kill) restart'ta kaldığı yerden resume eder.
Gerçek ajan mantığı sonra; bu sadece iskeletin ucuca çalıştığını gösterir.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    goal: str
    steps: list[str]


def plan(state: State) -> State:
    return {"goal": state["goal"], "steps": state.get("steps", []) + ["plan: hedef ayrıştırıldı"]}


def execute(state: State) -> State:
    return {"goal": state["goal"], "steps": state["steps"] + ["execute: iş tamamlandı"]}


def build_graph():
    g = StateGraph(State)
    g.add_node("plan", plan)
    g.add_node("execute", execute)
    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", END)
    return g
