from pathlib import Path
from fpdf import FPDF

class StarPolicyPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, 'StarHealth Optima Comprehensive Policy Document', 0, 1, 'R')
        self.line(10, 18, 200, 18)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()} of 3 | Policy Reference: STAR-OPT-2026', 0, 0, 'C')

def generate_star_policy():
    pdf = StarPolicyPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # Page 1: Particulars
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 18)
    pdf.cell(0, 12, 'STARHEALTH OPTIMA HEALTH POLICY', 0, 1, 'C')
    pdf.set_font('Helvetica', 'I', 11)
    pdf.cell(0, 6, 'Annual Health Plan Terms', 0, 1, 'C')
    pdf.ln(8)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'SECTION 1: POLICY PARTICULARS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "1.1 Insurance Undertaking: StarHealth Allied Insurance issues this policy. Sum Insured is fixed at INR 1,000,000 (Rupees Ten Lakhs).\n"
        "1.2 Entry Age: Adults from age 18 to 75 years are eligible."
    )
    pdf.ln(4)

    # Page 2: Waiting Periods
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'SECTION 2: STARHEALTH WAITING PERIODS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "2.1 Pre-Existing Disease Waiting Period: A mandatory waiting period of 48 months applies to pre-existing conditions.\n"
        "2.2 Cataract Surgery Waiting Period: Cataract operations have a waiting period of 24 months, with a maximum claim cap of INR 25,000 per eye."
    )
    pdf.ln(4)

    # Page 3: Exclusions & Claims
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'SECTION 3: PERMANENT EXCLUSIONS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "3.1 Maternity Exclusions: Under StarHealth Optima, maternity, pregnancy, and childbirth expenses are strictly excluded and not covered under any circumstances."
    )
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 8, 'SECTION 4: CLAIM SUBMISSION', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "4.1 Reimbursement Claims: All original StarHealth claim forms and hospital bills must be lodged within 15 days of discharge."
    )

    out_path = Path(__file__).resolve().parent / "StarHealth_Optima_Policy.pdf"
    pdf.output(str(out_path))
    print(f"StarHealth policy generated at: {out_path}")

if __name__ == "__main__":
    generate_star_policy()
