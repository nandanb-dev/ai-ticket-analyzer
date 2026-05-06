import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from agents.test_case_agent import run_testcase_agent

router = APIRouter(prefix="/testcases", tags=["testcases"])


class TestCaseRequest(BaseModel):
    story: str
    acceptance_criteria: List[str]


@router.post("")
async def generate_testcases(req: TestCaseRequest):

    try:
        result = await anyio.to_thread.run_sync(
            lambda: run_testcase_agent(
                story=req.story,
                acceptance_criteria=req.acceptance_criteria
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"test_cases": result}