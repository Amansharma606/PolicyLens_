import os
from pathlib import Path
from fpdf import FPDF

class PolicyPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, 'CareShield Comprehensive Health Insurance Policy (PolicyLens Reference)', 0, 1, 'R')
        self.line(10, 18, 200, 18)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()} of 5 | Policy Document Reference: CS-HLTH-2026-V4', 0, 0, 'C')

def create_sample_policy():
    pdf = PolicyPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # -------------------------------------------------------------
    # PAGE 1: PREAMBLE, OVERVIEW & ELIGIBILITY
    # -------------------------------------------------------------
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 12, 'CARESHIELD HEALTH INSURANCE POLICY', 0, 1, 'C')
    pdf.set_font('Helvetica', 'I', 11)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 6, 'Standard Terms, Conditions, and Benefit Schedule', 0, 1, 'C')
    pdf.ln(8)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 1: POLICY OVERVIEW AND PREAMBLE', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5.5, 
        "1.1 Policy Agreement: CareShield General Insurance Company enters into this contract of insurance based upon the proposal form, declarations, and medical information submitted by the Policyholder. This policy provides indemnity and fixed medical reimbursement for covered hospitalization expenses incurred within the geographical territory of India.\n"
        "1.2 Sum Insured: The basic Sum Insured under this policy is INR 500,000 (Rupees Five Lakhs) per individual/floater per policy year, subject to cumulative bonus restorations.\n"
        "1.3 Policy Period: The standard duration of this health insurance policy is twelve (12) calendar months from the inception date."
    )
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 2: POLICYHOLDER ELIGIBILITY AND ENTRY AGE', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "2.1 Adult Eligibility: Any person residing in India between the ages of 18 years and 65 years is eligible to enroll as a primary policyholder or insured spouse under this plan.\n"
        "2.2 Dependent Children: Dependent children aged between 91 days and 25 years can be covered under the family floater plan, provided they are financially dependent and unmarried.\n"
        "2.3 Lifelong Renewability: The policy offers guaranteed lifelong renewability subject to timely premium payment before the expiration of the 30-day grace period."
    )

    # -------------------------------------------------------------
    # PAGE 2: IN-PATIENT HOSPITALIZATION & BENEFITS
    # -------------------------------------------------------------
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 3: COVERAGE AND IN-PATIENT BENEFITS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5.5,
        "3.1 In-Patient Hospitalization: If the Insured Person is admitted to a registered Hospital for medically necessary treatment for a minimum consecutive period of 24 hours, the Company will cover Room Rent, Boarding Expenses, Nursing care, Medical Practitioner fees, and Anesthetist charges up to the Sum Insured.\n"
        "3.2 Room Rent Sub-Limit: Room rent coverage is capped at 1% of the Sum Insured per day (INR 5,000/day) for standard private rooms, and Intensive Care Unit (ICU) charges are capped at 2% of the Sum Insured per day (INR 10,000/day).\n"
        "3.3 Day Care Procedures: Medical treatments requiring less than 24 hours of hospitalization due to advanced technological and surgical advancements (e.g. Chemotherapy, Radiotherapy, Hemodialysis, Cataract surgery) are covered up to the Sum Insured.\n"
        "3.4 Pre and Post Hospitalization Expenses: Medical expenses incurred 60 days immediately prior to hospital admission and 90 days following hospital discharge are covered, provided they relate to the same medical condition.\n"
        "3.5 Road Ambulance Cover: Expenses up to INR 2,500 per hospitalization are reimbursed for emergency road ambulance transportation to the nearest network hospital."
    )
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 4: MATERNITY BENEFIT AND NEWBORN EXTENSION', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "4.1 Maternity Expenses: Yes, maternity and childbirth expenses are covered under this policy for female insured persons. The benefit covers normal delivery charges up to INR 50,000 and Caesarean section (C-Section) delivery charges up to INR 75,000.\n"
        "4.2 Newborn Baby Coverage: Hospitalization expenses for the newborn baby are covered from day one up to the maternity limit until the renewal of the policy.\n"
        "4.3 Maternity Waiting Period: Maternity benefits are payable only after a continuous policy waiting period of 24 months has elapsed from the initial policy inception date."
    )

    # -------------------------------------------------------------
    # PAGE 3: WAITING PERIODS
    # -------------------------------------------------------------
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 5: WAITING PERIODS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5.5,
        "5.1 Initial 30-Day Waiting Period: Any illness or disease diagnosed or requiring hospitalization within the first thirty (30) days from the policy inception date is strictly excluded from coverage, except for emergency hospitalizations arising directly from accidental bodily injury.\n"
        "5.2 Specific Illness Waiting Period (24 Months): A specific waiting period of 24 consecutive months of continuous coverage applies to treatments including: Cataract surgeries, Benign Prostatic Hypertrophy, Hernia, Hydrocele, Hysterectomy for menorrhagia, Piles, Sinusitis, Joint replacement surgeries, and Calculus diseases of the biliary and urinary systems.\n"
        "5.3 Pre-Existing Disease (PED) Waiting Period (36 Months): Any pre-existing disease, medical condition, or symptom declared or diagnosed prior to policy inception shall have a mandatory waiting period of 36 months of continuous coverage before claim reimbursement is admissible.\n"
        "5.4 Maternity Waiting Period (24 Months): As specified in Section 4.3, a continuous waiting period of 24 months applies before any delivery or obstetric expenses can be claimed."
    )
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 6: CATARACT SUB-LIMITS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "6.1 Cataract Limit: The company's total liability for Cataract surgery is limited to INR 40,000 per eye or actual expenses, whichever is lower, subject to the 24-month waiting period specified in Clause 5.2."
    )

    # -------------------------------------------------------------
    # PAGE 4: EXCLUSIONS
    # -------------------------------------------------------------
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 7: PERMANENT POLICY EXCLUSIONS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5.5,
        "The Company shall not be liable to make any payment under this policy in respect of any expenses incurred by the Insured Person directly or indirectly for:\n"
        "7.1 Cosmetic and Aesthetic Surgeries: Cosmetic, plastic, or reconstructive surgeries performed for beauty enhancement, rhinoplasty, or aesthetic reasons without underlying traumatic injury or burns.\n"
        "7.2 Self-Inflicted Injury and Substance Abuse: Treatment resulting directly from intentional self-harm, attempted suicide, alcohol abuse, or intoxication from narcotics.\n"
        "7.3 Maternity Exclusions: Infertility, sub-fertility treatments, in-vitro fertilization (IVF), surrogate or gestational maternity, voluntary termination of pregnancy during the first 12 weeks, and stem cell harvesting are strictly excluded.\n"
        "7.4 Unproven and Experimental Treatments: Treatments, therapies, and medications that lack medical validation from the Indian Medical Council or recognized national drug authorities.\n"
        "7.5 Dental Care: Dental surgeries, fillings, or dentures are excluded unless requiring emergency inpatient hospitalization resulting from accidental injury.\n"
        "7.6 War and Nuclear Perils: Hospitalization arising from war, civil invasion, mutiny, rebellion, or nuclear radiation contamination."
    )

    # -------------------------------------------------------------
    # PAGE 5: CLAIMS PROCESS & REQUIRED DOCUMENTS
    # -------------------------------------------------------------
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 8: CLAIM PROCESS AND MANDATORY DOCUMENTS', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5.5,
        "8.1 Cashless Facility: Cashless treatment is available across 10,000+ networked hospitals. The insured must obtain pre-authorization from the Third Party Administrator (TPA) at least 48 hours prior to planned admission, or within 24 hours of emergency admission.\n"
        "8.2 Reimbursement Claim Intimation: In non-network hospitals, claim intimation must be submitted to the Company within 48 hours of admission. Complete claim documents must be submitted within 30 days following hospital discharge.\n"
        "8.3 Mandatory Documents for Reimbursement Claims:\n"
        "   a) Duly filled and signed CareShield Claim Form.\n"
        "   b) Original hospital discharge summary detailing admission notes, treatment course, and final diagnosis.\n"
        "   c) Original itemized hospital bills with detailed breakdown of room rent, nursing, and medicines.\n"
        "   d) Payment receipts with revenue stamp.\n"
        "   e) Doctor prescriptions and original diagnostic investigation reports (blood tests, pathology, radiology).\n"
        "   f) Pharmacy bills along with doctor's prescription.\n"
        "   g) Copy of KYC documents and cancelled cheque of the Policyholder for NEFT transfer."
    )
    pdf.ln(4)

    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, 'SECTION 9: GRIEVANCE REDRESSAL AND OMBUDSMAN', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 5.5,
        "9.1 Grievance Redressal: If the policyholder has any dispute regarding claim settlement, they may write to the Grievance Redressal Officer at grievance@careshield.co.in. If unresolved within 15 days, the claim may be escalated to the Insurance Ombudsman under the Insurance Regulatory and Development Authority (IRDAI) guidelines."
    )

    output_dir = Path(__file__).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / "CareShield_Health_Insurance_Policy.pdf"
    pdf.output(str(pdf_path))
    print(f"Sample Policy PDF created successfully at: {pdf_path}")
    return pdf_path

if __name__ == "__main__":
    create_sample_policy()
