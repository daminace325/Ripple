from pydantic import BaseModel


class FollowRequest(BaseModel):
    followee_id: int


class FollowResponse(BaseModel):
    followee_id: int
    following: bool
