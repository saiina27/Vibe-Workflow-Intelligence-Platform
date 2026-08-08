from app.models.enums import TaskComplexity, TaskType


class TaskClassifier:

    def classify(
        self,
        prompt: str,
    ) -> TaskType:

        prompt = prompt.lower()

        if self._is_code(prompt):
            return TaskType.CODE

        if self._is_document(prompt):
            return TaskType.DOCUMENT

        if self._is_analysis(prompt):
            return TaskType.ANALYSIS

        if self._is_decision(prompt):
            return TaskType.DECISION

        if self._is_suggestion(prompt):
            return TaskType.SUGGESTION

        if self._is_memory(prompt):
            return TaskType.MEMORY

        if self._is_search(prompt):
            return TaskType.SEARCH

        if self._is_image(prompt):
            return TaskType.IMAGE

        return TaskType.CHAT

    def classify_complexity(
        self,
        prompt: str,
    ) -> TaskComplexity:

        prompt = prompt.lower()

        if self._is_complex(prompt):
            return TaskComplexity.COMPLEX

        if self._is_moderate(prompt):
            return TaskComplexity.MODERATE

        return TaskComplexity.SIMPLE

    def _is_complex(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "architecture",
            "production",
            "system design",
            "distributed",
            "microservices",
            "multi-agent",
            "scalable",
            "optimization",
            "optimize",
            "deep dive",
            "advanced",
            "complex",
            "end-to-end",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_moderate(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "implement",
            "build",
            "debug",
            "refactor",
            "integrate",
            "explain",
            "compare",
            "analyze",
            "design",
            "write",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_code(
        self,
        prompt: str,
    ) -> bool:

        code_keywords = [
            "code",
            "function",
            "class",
            "algorithm",
            "api",
            "bug",
            "debug",
            "implement",
            "program",
            "script",
            "syntax",
            "exception",
            "error",
            "refactor",
            "compile",
        ]

        language_keywords = [
            "python",
            "java",
            "javascript",
            "typescript",
            "c++",
            "fastapi",
            "sql",
        ]

        has_code_keyword = any(
            keyword in prompt
            for keyword in code_keywords
        )

        has_language_keyword = any(
            keyword in prompt
            for keyword in language_keywords
        )

        code_actions = [
            "write",
            "create",
            "build",
            "implement",
            "develop",
            "fix",
            "debug",
            "generate",
            "run",
        ]

        has_code_action = any(
            action in prompt
            for action in code_actions
        )

        return (
            has_code_keyword
            or (
                has_language_keyword
                and has_code_action
            )
        )

    def _is_document(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "email",
            "document",
            "pdf",
            "resume",
            "rewrite",
            "summarize",
            "summary",
            "grammar",
            "translate",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_analysis(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "analyze",
            "analysis",
            "compare",
            "evaluate",
            "explain",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_decision(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "should i",
            "which is better",
            "choose",
            "decision",
            "recommend",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_suggestion(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "suggest",
            "ideas",
            "recommendation",
            "best practices",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_memory(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "remember",
            "recall",
            "memory",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_search(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "search",
            "find",
            "lookup",
            "google",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )

    def _is_image(
        self,
        prompt: str,
    ) -> bool:

        keywords = [
            "image",
            "photo",
            "picture",
            "draw",
            "logo",
        ]

        return any(
            keyword in prompt
            for keyword in keywords
        )


task_classifier = TaskClassifier()