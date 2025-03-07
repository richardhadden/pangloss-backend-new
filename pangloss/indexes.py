import asyncio
import typing

from rich import print

from pangloss.database import Database
from pangloss.model_config.model_manager import ModelManager

if typing.TYPE_CHECKING:
    from pangloss.models import BaseNode


class IndexAnnotation:
    def __hash__(self):
        return 0


class Index(IndexAnnotation):
    pass


class Unique(IndexAnnotation):
    pass


class TextIndex(IndexAnnotation):
    pass


class FullTextIndex(IndexAnnotation):
    pass


class OmitFromNodeFullTextIndex(IndexAnnotation):
    pass


def get_string_fields(model: type["BaseNode"]) -> list[str]:
    string_fields = []
    for field_name, field in model.model_fields.items():
        try:
            annotated_type, *annotations = typing.get_args(field.annotation)
            annotated_string = annotated_type == str and not any(
                isinstance(ann, OmitFromNodeFullTextIndex)
                or ann is OmitFromNodeFullTextIndex
                for ann in annotations
            )
        except ValueError:
            pass

        if field.annotation == str or annotated_string:
            string_fields.append(field_name)

    return string_fields


def create_index_queries():
    queries = [
        "CREATE INDEX HeadNodeID FOR (n:BaseNode) ON (n.head_node)",
        "CREATE INDEX HeadNodeType FOR (n:BaseNode) ON (n.head_node)",
        "CREATE CONSTRAINT BaseNodeIdUnique IF NOT EXISTS FOR (n:BaseNode) REQUIRE n.id IS UNIQUE",
        """CREATE CONSTRAINT PGUserNameIndex IF NOT EXISTS FOR (n:PGUser) REQUIRE n.username IS UNIQUE""",
        """CREATE FULLTEXT INDEX BaseNodeFullTextIndex 
                IF NOT EXISTS FOR (n:BaseNode) ON EACH [n.label]
                OPTIONS {
                    indexConfig: {
                        `fulltext.analyzer`: 'standard-no-stop-words',
                        `fulltext.eventually_consistent`: true
                    }
                }""",
    ]
    print(
        "Creating Constraint: [green bold]PGUser[/green bold].[blue bold]username[/blue bold] must be unique",
    )
    print(
        "Creating Constraint: [green bold]BaseNode[/green bold].[blue bold]uuid[/blue bold] must be unique",
    )

    for model in ModelManager.base_models.values():
        string_fields = ["label"]  # get_string_fields(model)
        string_fields_query = ", ".join(
            f"n.{field_name}" for field_name in string_fields
        )

        queries.extend(
            [
                f"""CREATE FULLTEXT INDEX {model.__name__}FullTextIndex 
                IF NOT EXISTS FOR (n:{model.__name__}) ON EACH [{string_fields_query}]
                OPTIONS {{
                    indexConfig: {{
                        `fulltext.analyzer`: 'standard-no-stop-words',
                        `fulltext.eventually_consistent`: true
                    }}
                }}
                """,
            ]
        )
        print(
            f"Creating Full Text Index for [green bold]{model.__name__}[/green bold] on fields {', '.join(f'[blue bold]{f}[/blue bold]' for f in string_fields)}"
        )
    return queries


async def _install_index_and_constraints_from_text():
    queries = create_index_queries()
    for query in queries:
        try:
            await Database._cypher_write(query, {})
        except Exception as e:
            print(e)


def install_indexes_and_constraints():
    queries = create_index_queries()

    async def _run(queries):
        async def _run_query(query):
            try:
                await Database._cypher_write(query, {})
            except Exception as e:
                print(e)

        await asyncio.gather(*[_run_query(query) for query in queries])

    asyncio.run(_run(queries))
