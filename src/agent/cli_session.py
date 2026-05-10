from typing import Any, Callable, Dict


WORKFLOW_STRUCTURE_TEXT = """
    START
      ↓
     query_classification_node
      ↓
    [Route based on classification]
      ↓
    DATABASE Route:
      ↓
     list_tables_node (discover available tables)
      ↓
     get_schema_node (retrieve table schemas)
      ↓
     generate_sql_node (generate SQL query)
      ↓
     validate_sql_node (validate SQL syntax)
      ↓
     execute_sql_node (execute query on database)
      ↓
     generate_response_node (format final response)
      ↓
    END

    CONVERSATIONAL Route:
      ↓
     generate_response_node (direct conversational response)
      ↓
    END

    SCHEMA Route:
      ↓
     list_tables_node (table discovery only)
      ↓
     generate_response_node (schema information response)
      ↓
    END

     Features:
    • PostgreSQL with 15 specialized tables
    • Intelligent table selection (mortes, procedimentos, etc.)
    • OpenAI tool calling (gpt-4o / gpt-4o-mini)
    • Retry mechanisms with error recovery
    • Healthcare domain optimization (SUS data)
"""


class WorkflowVisualizer:
    """LangGraph workflow visualization helpers."""

    @staticmethod
    def get_workflow_visualization(workflow: Any, xray: bool = True) -> bytes:
        if not workflow:
            raise ValueError("Workflow not initialized")
        return workflow.get_graph(xray=xray).draw_mermaid_png()

    @staticmethod
    def display_workflow(workflow: Any, logger: Any, xray: bool = True) -> None:
        try:
            from IPython.display import Image, display

            display(Image(WorkflowVisualizer.get_workflow_visualization(workflow, xray=xray)))
        except ImportError:
            logger.warning("IPython not available. Use save_workflow_diagram() instead.")

    @staticmethod
    def save_workflow_diagram(
        workflow: Any,
        logger: Any,
        filename: str = "workflow.png",
        xray: bool = True,
    ) -> None:
        try:
            png_data = WorkflowVisualizer.get_workflow_visualization(workflow, xray=xray)
            with open(filename, "wb") as file_obj:
                file_obj.write(png_data)
            logger.info("Workflow diagram saved", extra={"filename": filename})
        except Exception as exc:
            try:
                graph = workflow.get_graph(xray=xray)
                mermaid_text = graph.draw_mermaid()
                alt_filename = filename.rsplit(".", 1)[0] + ".mmd"
                with open(alt_filename, "w", encoding="utf-8") as file_obj:
                    file_obj.write(mermaid_text)
                logger.warning(
                    "PNG render unavailable; saved Mermaid source instead",
                    extra={"filename": alt_filename, "error": str(exc)},
                )
            except Exception as fallback_exc:
                logger.error(
                    "Failed to save workflow diagram (PNG and Mermaid fallback)",
                    extra={"error": f"{exc}; fallback_error={fallback_exc}"},
                )

    @staticmethod
    def print_workflow_structure(
        workflow: Any,
        logger: Any,
        print_fn: Callable[[str], None] = print,
    ) -> None:
        if not workflow:
            logger.error("Workflow not initialized")
            return

        print_fn("LangGraph Text2SQL Workflow Structure:")
        print_fn("=" * 60)
        print_fn(WORKFLOW_STRUCTURE_TEXT)


class InteractiveSession:
    """Interactive CLI session helper."""

    @staticmethod
    def start(
        orchestrator: Any,
        logger: Any,
        environment: str,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
    ) -> None:
        import time

        logger.info("Starting interactive session")
        print_fn(" TXT2SQL - Sessão Interativa (LangGraph)")
        print_fn("=" * 60)
        print_fn("Digite 'sair', 'exit' ou 'quit' para encerrar")
        print_fn("=" * 60)

        session_id = f"interactive_{int(time.time() * 1000) % 100000}"

        while True:
            try:
                user_input = input_fn("\n Sua pergunta: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["sair", "exit", "quit"]:
                    logger.info("Interactive session ended by user")
                    print_fn("\n Até logo!")
                    break

                result = orchestrator.process_query(
                    user_query=user_input,
                    session_id=session_id,
                    streaming=False,
                    run_name=f"interactive_query_{session_id}",
                    tags=["interactive", "cli"],
                    metadata={"source": "cli_interactive", "environment": environment},
                )

                InteractiveSession._print_result(result, print_fn)
            except KeyboardInterrupt:
                logger.info("Interactive session interrupted by user")
                print_fn("\n\n Até logo!")
                break
            except Exception as exc:
                logger.error("Interactive session error", extra={"error": str(exc)})
                print_fn(f"\n Erro interno: {str(exc)}")

    @staticmethod
    def _print_result(
        result: Dict[str, Any],
        print_fn: Callable[[str], None] = print,
    ) -> None:
        if isinstance(result, dict) and result.get("success"):
            response_text = result.get("response") or "(sem resposta)"
            print_fn(f"\n {response_text}")
            if result.get("sql_query"):
                print_fn(f" SQL: {result['sql_query']}")
            if result.get("chart"):
                import json

                print_fn(" ChartSpec:")
                print_fn(json.dumps(result["chart"], ensure_ascii=False, indent=2))
            if result.get("execution_time") is not None:
                try:
                    print_fn(f" Tempo: {float(result['execution_time']):.2f}s")
                except Exception:
                    return
            return

        error_msg = result.get("error_message") if isinstance(result, dict) else str(result)
        print_fn(f"\n Erro: {error_msg}")
