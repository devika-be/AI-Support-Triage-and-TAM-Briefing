from app.data_loader import load_kb_documents, load_tickets
from app.retrieval import retrieve_for_ticket


def main() -> None:
    tickets = load_tickets()
    kb_documents = load_kb_documents()

    sample_ids = {"TKT-10004", "TKT-10015"}
    for ticket in tickets:
        if ticket.ticket_id not in sample_ids:
            continue

        print(f"\n=== {ticket.ticket_id} | {ticket.subject} ===")
        results = retrieve_for_ticket(ticket, documents=kb_documents, top_k=2)
        for result in results:
            print(f"- {result.doc_path} :: {result.heading} :: score={result.score}")
            print(f"  excerpt: {result.excerpt}")
            if result.matched_error_codes:
                print(f"  matched_error_codes: {result.matched_error_codes}")


if __name__ == "__main__":
    main()
