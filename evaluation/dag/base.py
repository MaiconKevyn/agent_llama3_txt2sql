"""
Base DAG Implementation for Evaluation Pipeline

Provides lightweight DAG structure using NetworkX for task orchestration
and visualization.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx


@dataclass
class TaskResult:
    """Result of a task execution"""
    task_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TaskDefinition:
    """Definition of a task in the DAG"""
    name: str
    func: Callable
    depends_on: List[str]
    description: Optional[str] = None


class EvaluationDAG:
    """
    Lightweight DAG for evaluation pipeline orchestration

    Features:
    - Task dependency management
    - Topological execution order
    - Cycle detection
    - Visual DAG generation
    - Execution tracking
    """

    def __init__(self, name: str = "Evaluation Pipeline"):
        """
        Initialize DAG

        Args:
            name: Name of the pipeline
        """
        self.name = name
        self.graph = nx.DiGraph()
        self.tasks: Dict[str, TaskDefinition] = {}
        self.results: Dict[str, TaskResult] = {}
        self.logger = self._create_logger()

    def add_task(
        self,
        name: str,
        func: Callable,
        depends_on: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> None:
        """
        Add a task to the DAG

        Args:
            name: Unique task identifier
            func: Task function to execute
            depends_on: List of task names this task depends on
            description: Optional task description

        Raises:
            ValueError: If task name already exists or dependencies are invalid
        """
        if name in self.tasks:
            raise ValueError(f"Task '{name}' already exists in DAG")

        depends_on = depends_on or []

        # Validate dependencies exist
        for dep in depends_on:
            if dep not in self.tasks:
                raise ValueError(f"Dependency '{dep}' not found for task '{name}'")

        # Add task definition
        self.tasks[name] = TaskDefinition(
            name=name,
            func=func,
            depends_on=depends_on,
            description=description
        )

        # Add to graph
        self.graph.add_node(name, description=description)

        # Add edges for dependencies
        for dep in depends_on:
            self.graph.add_edge(dep, name)

        self.logger.debug(f"Added task '{name}' with {len(depends_on)} dependencies")

    def validate(self) -> bool:
        """
        Validate DAG structure

        Returns:
            True if DAG is valid (acyclic), False otherwise
        """
        if not nx.is_directed_acyclic_graph(self.graph):
            self.logger.error("DAG contains cycles - invalid structure")
            try:
                cycle = nx.find_cycle(self.graph)
                self.logger.error(f"Cycle detected: {cycle}")
            except:
                pass
            return False

        self.logger.info("DAG validation successful - no cycles detected")
        return True

    def get_execution_order(self) -> List[str]:
        """
        Get topologically sorted execution order

        Returns:
            List of task names in execution order
        """
        return list(nx.topological_sort(self.graph))

    def execute(self, initial_data: Optional[Dict[str, Any]] = None) -> Dict[str, TaskResult]:
        """
        Execute all tasks in topological order

        Args:
            initial_data: Optional initial data to pass to first tasks

        Returns:
            Dictionary of task results

        Raises:
            RuntimeError: If DAG is invalid or task execution fails critically
        """
        # Validate DAG
        if not self.validate():
            raise RuntimeError("Cannot execute invalid DAG")

        # Reset results
        self.results = {}
        initial_data = initial_data or {}

        # Get execution order
        execution_order = self.get_execution_order()

        self.logger.info(f"{'='*80}")
        self.logger.info(f"EXECUTING DAG: {self.name}")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Total tasks: {len(execution_order)}")
        self.logger.info(f"Execution order: {' → '.join(execution_order)}")
        self.logger.info(f"{'='*80}\n")

        start_time = time.time()

        # Execute each task
        for i, task_name in enumerate(execution_order, 1):
            task_def = self.tasks[task_name]

            self.logger.info(f"[{i}/{len(execution_order)}] Executing: {task_name}")
            if task_def.description:
                self.logger.info(f"    Description: {task_def.description}")

            # Prepare task inputs from dependencies
            task_inputs = {}
            dependency_failed = False

            # Add initial data
            task_inputs.update(initial_data)

            # Add results from dependencies
            for dep_name in task_def.depends_on:
                if dep_name in self.results:
                    dep_result = self.results[dep_name]
                    if dep_result.success:
                        task_inputs[dep_name] = dep_result.data
                    else:
                        # Dependency failed
                        error_msg = f"Dependency '{dep_name}' failed"
                        self.logger.error(f"    ❌ {error_msg}")

                        self.results[task_name] = TaskResult(
                            task_name=task_name,
                            success=False,
                            error=error_msg
                        )
                        dependency_failed = True
                        break

            if dependency_failed:
                continue

            # Execute task
            task_start = time.time()
            try:
                result_data = task_def.func(**task_inputs)
                execution_time = (time.time() - task_start) * 1000

                self.results[task_name] = TaskResult(
                    task_name=task_name,
                    success=True,
                    data=result_data,
                    execution_time_ms=execution_time
                )

                self.logger.info(f"    ✅ Success ({execution_time:.1f}ms)")

            except Exception as e:
                execution_time = (time.time() - task_start) * 1000
                error_msg = str(e)

                self.logger.error(f"    ❌ Failed: {error_msg}")

                self.results[task_name] = TaskResult(
                    task_name=task_name,
                    success=False,
                    error=error_msg,
                    execution_time_ms=execution_time
                )

                # Continue with remaining tasks
                continue

        total_time = time.time() - start_time

        # Summary
        successful_tasks = sum(1 for r in self.results.values() if r.success)
        failed_tasks = len(self.results) - successful_tasks

        self.logger.info(f"\n{'='*80}")
        self.logger.info("DAG EXECUTION COMPLETED")
        self.logger.info(f"{'='*80}")
        self.logger.info(f"Total time: {total_time:.2f}s")
        self.logger.info(f"Successful tasks: {successful_tasks}/{len(execution_order)}")
        self.logger.info(f"Failed tasks: {failed_tasks}/{len(execution_order)}")
        self.logger.info(f"{'='*80}\n")

        return self.results

    def visualize(
        self,
        output_path: str = "evaluation_dag.png",
        show_descriptions: bool = True,
        figsize: tuple = (16, 10)
    ) -> None:
        """
        Generate visual representation of the DAG

        Args:
            output_path: Path to save visualization
            show_descriptions: Include task descriptions in visualization
            figsize: Figure size (width, height)
        """
        if len(self.graph.nodes) == 0:
            self.logger.warning("Cannot visualize empty DAG")
            return

        self.logger.info(f"Generating DAG visualization: {output_path}")

        # Create figure
        plt.figure(figsize=figsize)

        # Use hierarchical layout for better DAG visualization
        try:
            # Try graphviz first (best for DAGs)
            pos = nx.nx_pydot.graphviz_layout(self.graph, prog='dot')
        except:
            try:
                # Fallback to manual hierarchical layout
                pos = self._hierarchical_layout(self.graph)
            except:
                # Last resort: spring layout with better parameters
                pos = nx.spring_layout(self.graph, k=3, iterations=100, seed=42)

        # Determine node colors based on execution results
        node_colors = []
        for node in self.graph.nodes():
            if node in self.results:
                result = self.results[node]
                if result.success:
                    node_colors.append('#90EE90')  # Light green
                else:
                    node_colors.append('#FFB6C6')  # Light red
            else:
                node_colors.append('#87CEEB')  # Sky blue (not executed)

        # Draw graph
        nx.draw_networkx_nodes(
            self.graph, pos,
            node_color=node_colors,
            node_size=3500,
            alpha=0.9,
            edgecolors='black',
            linewidths=2
        )

        nx.draw_networkx_edges(
            self.graph, pos,
            edge_color='gray',
            arrows=True,
            arrowsize=20,
            arrowstyle='->',
            width=2,
            connectionstyle='arc3,rad=0.1'
        )

        # Draw labels
        nx.draw_networkx_labels(
            self.graph, pos,
            font_size=9,
            font_weight='bold',
            font_family='sans-serif'
        )

        # Add descriptions as text below nodes if requested
        if show_descriptions:
            for node, (x, y) in pos.items():
                task_def = self.tasks.get(node)
                if task_def and task_def.description:
                    plt.text(
                        x, y - 50,  # Offset below node
                        task_def.description[:40] + '...' if len(task_def.description) > 40 else task_def.description,
                        ha='center',
                        fontsize=7,
                        style='italic',
                        color='gray'
                    )

        # Add legend
        legend_elements = [
            mpatches.Patch(color='#87CEEB', label='Not Executed'),
            mpatches.Patch(color='#90EE90', label='Success'),
            mpatches.Patch(color='#FFB6C6', label='Failed')
        ]
        plt.legend(handles=legend_elements, loc='upper right', fontsize=10)

        # Title
        plt.title(f"{self.name}\n({len(self.graph.nodes)} tasks, {len(self.graph.edges)} dependencies)",
                 fontsize=14, fontweight='bold', pad=20)

        plt.axis('off')
        plt.tight_layout()

        # Save
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()

        self.logger.info(f"✅ DAG visualization saved to: {output_path}")

    def get_task_info(self, task_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a task

        Args:
            task_name: Name of the task

        Returns:
            Dictionary with task information
        """
        if task_name not in self.tasks:
            raise ValueError(f"Task '{task_name}' not found")

        task_def = self.tasks[task_name]

        info = {
            'name': task_name,
            'description': task_def.description,
            'dependencies': task_def.depends_on,
            'dependents': list(self.graph.successors(task_name)),
            'executed': task_name in self.results
        }

        if task_name in self.results:
            result = self.results[task_name]
            info.update({
                'success': result.success,
                'execution_time_ms': result.execution_time_ms,
                'error': result.error,
                'timestamp': result.timestamp
            })

        return info

    def print_summary(self) -> None:
        """Print detailed summary of DAG structure and results"""
        print(f"\n{'='*80}")
        print(f"DAG SUMMARY: {self.name}")
        print(f"{'='*80}")
        print("\nStructure:")
        print(f"  Total tasks: {len(self.tasks)}")
        print(f"  Total dependencies: {len(self.graph.edges)}")

        if self.results:
            successful = sum(1 for r in self.results.values() if r.success)
            failed = len(self.results) - successful

            print("\nExecution:")
            print(f"  Executed tasks: {len(self.results)}")
            print(f"  Successful: {successful}")
            print(f"  Failed: {failed}")

            total_time = sum(r.execution_time_ms for r in self.results.values())
            print(f"  Total execution time: {total_time:.1f}ms")

        print("\nExecution Order:")
        for i, task_name in enumerate(self.get_execution_order(), 1):
            status = ""
            if task_name in self.results:
                result = self.results[task_name]
                status = " ✅" if result.success else " ❌"
            print(f"  {i}. {task_name}{status}")

        print(f"{'='*80}\n")

    def _hierarchical_layout(self, graph: nx.DiGraph) -> Dict[str, tuple]:
        """
        Create hierarchical layout for DAG visualization

        Positions nodes in layers based on topological levels

        Args:
            graph: NetworkX directed graph

        Returns:
            Dictionary mapping node names to (x, y) positions
        """
        # Get topological generations (levels)
        levels = list(nx.topological_generations(graph))

        pos = {}
        y_spacing = 100
        x_spacing = 150

        for level_idx, level_nodes in enumerate(levels):
            level_nodes = list(level_nodes)
            num_nodes = len(level_nodes)

            # Calculate y position (top to bottom)
            y = -level_idx * y_spacing

            # Calculate x positions (centered)
            total_width = (num_nodes - 1) * x_spacing
            start_x = -total_width / 2

            for node_idx, node in enumerate(level_nodes):
                x = start_x + node_idx * x_spacing
                pos[node] = (x, y)

        return pos

    def _create_logger(self) -> logging.Logger:
        """Create logger for the DAG"""
        logger = logging.getLogger(f'EvaluationDAG.{self.name}')

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

        return logger
