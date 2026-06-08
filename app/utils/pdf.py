import io
from pathlib import Path
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

from app.models.booking import Booking
from app.models.event import Event
from app.models.user import User
from app.models.venue import Venue

def generate_ticket_pdf(
    booking: Booking, event: Event, venue: Venue, user: User, qr_bytes: bytes
) -> bytes:
    """Generates a ticket PDF using ReportLab natively."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "Event Ticket")
    
    # Details
    c.setFont("Helvetica", 14)
    c.drawString(100, 710, f"Event: {event.title}")
    c.drawString(100, 690, f"Venue: {venue.name}")
    start_date = event.start_datetime.strftime("%B %d, %Y")
    start_time = event.start_datetime.strftime("%H:%M")
    c.drawString(100, 670, f"Date: {start_date} | Time: {start_time}")
    
    c.drawString(100, 640, f"Name: {user.full_name}")
    c.drawString(100, 620, f"Booking ID: {booking.id}")
    c.drawString(100, 600, f"Seats: {', '.join(booking.seat_ids)}")
    
    # QR Code
    qr_img = Image.open(io.BytesIO(qr_bytes))
    c.drawImage(ImageReader(qr_img), 400, 600, width=150, height=150)
    
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
