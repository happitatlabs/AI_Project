from fastapi import APIRouter

router = APIRouter()


@router.get("/review-queue")
def list_review_queue(review_required: bool = True, display_order: str = "priority_desc"):
    return {
        "review_required": review_required,
        "display_order": display_order,
    }


@router.post("/review-queue/{item_id}/ack")
def acknowledge_review(item_id: str):
    return {
        "item_id": item_id,
        "status": "acknowledged",
    }
