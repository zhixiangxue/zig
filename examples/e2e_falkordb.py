from __future__ import annotations

import asyncio

from zig import Graph


async def main() -> None:
    g = Graph("falkordb://localhost:6379/programs")

    await g.execute("MATCH (n) DETACH DELETE n")

    g.node.add("Program", id="p1", properties={"name": "MyHome", "amount": 50000})
    g.node.add("Agency", id="a1", properties={"name": "CalHFA", "county": "Sacramento"})
    g.edge.add("p1", "OFFERED_BY", "a1", properties={"since": 2024, "source": "calhfa"})
    await g.commit()

    result = await g.execute(
        "MATCH (p:Program {id: 'p1'})-[r:OFFERED_BY]->(a:Agency {id: 'a1'}) "
        "RETURN p.name AS program, a.name AS agency, r.since AS since"
    )
    print(result.records)

    node = await g.node.get("p1")
    print(node)


if __name__ == "__main__":
    asyncio.run(main())
