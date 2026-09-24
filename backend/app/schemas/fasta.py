from pydantic import BaseModel


class FastaResult(BaseModel):
    sequence_id: str
    sequence_length: int
    fasta_content: str
