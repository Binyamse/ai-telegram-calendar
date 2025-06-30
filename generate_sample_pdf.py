import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

def create_sample_event_pdf(file_path="data/sample_event.pdf"):
    """Creates a sample PDF with event details."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
    except ImportError:
        print("Error: reportlab library not found.")
        print("Please install it using: pip install reportlab")
        return

    # Ensure the data directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, height - 1 * inch, "Upcoming Community Events")

    # Event 1
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, height - 1.5 * inch, "Project Sync-Up Meeting")
    c.setFont("Helvetica", 10)
    c.drawString(1.2 * inch, height - 1.7 * inch, "Date: July 20, 2025")
    c.drawString(1.2 * inch, height - 1.9 * inch, "Time: 10:30 AM - 11:30 AM")
    c.drawString(1.2 * inch, height - 2.1 * inch, "Location: Conference Room 4B")
    c.drawString(1.2 * inch, height - 2.3 * inch, "Description: Quarterly review of project milestones and planning for the next sprint.")

    # Event 2
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, height - 3 * inch, "Annual Tech Conference")
    c.setFont("Helvetica", 10)
    c.drawString(1.2 * inch, height - 3.2 * inch, "Date: August 18, 2025")
    c.drawString(1.2 * inch, height - 3.4 * inch, "Location: Downtown Convention Center")
    c.drawString(1.2 * inch, height - 3.6 * inch, "Description: Join us for the annual tech conference. Keynotes on AI, cloud, and more.")

    # Event 3
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, height - 4.3 * inch, "Team dinner")
    c.setFont("Helvetica", 10)
    c.drawString(1.2 * inch, height - 4.5 * inch, "Date: This Friday at 6:00 PM")
    c.drawString(1.2 * inch, height - 4.7 * inch, "Location: The Corner Bistro")
    c.drawString(1.2 * inch, height - 4.9 * inch, "Description: Casual team dinner to celebrate our recent launch.")

    c.save()
    print(f"Successfully created sample PDF: {file_path}")

if __name__ == "__main__":
    create_sample_event_pdf()
