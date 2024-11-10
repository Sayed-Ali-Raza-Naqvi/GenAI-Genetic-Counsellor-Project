import os
import streamlit as st
import requests
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import pagesizes, colors
import fitz
from groq import Groq
from docx import Document
import PyPDF2
from dotenv import load_dotenv


# load_dotenv()

# # Get the API key securely from the environment
# api_key = os.getenv("GROQ_API_KEY")
# if not api_key:
#     raise ValueError("API key not found. Make sure GROQ_API_KEY is set in the .env file.")

# Initialize the client
client = Groq(api_key="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")

def get_gene_info_ensembl(gene_name):
    """
    Fetches gene information from the Ensembl REST API.
    """
    url = f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene_name}?content-type=application/json"

    response = requests.get(url)

    if response.status_code == 200:
        gene_data = response.json()

        gene_info = {
            "Gene Name": gene_data.get("display_name", "N/A"),
            "Gene Symbol": gene_data.get("display_name", "N/A"),
            "Gene ID": gene_data.get("id", "N/A"),
            "Chromosome": gene_data.get("seq_region_name", "N/A"),
            "Start": gene_data.get("start", "N/A"),
            "End": gene_data.get("end", "N/A")
        }
        return gene_info
    else:
        print(f"Error fetching data from Ensembl for gene: {gene_name}")
        return None


def get_gene_function(gene_name):
    """
    Fetches the gene function from mygene.info API.
    """
    url = f"https://mygene.info/v3/query?q={gene_name}&fields=symbol,name,summary"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'hits' in data and len(data['hits']) > 0:
            gene_info = data['hits'][0]
            return {
                "symbol": gene_info.get("symbol", "N/A"),
                "name": gene_info.get("name", "N/A"),
                "summary": gene_info.get("summary", "No function available")
            }
    return None


def get_filtered_mutation_data_ensembl(gene_name, mutation_limit=5, mutation_type_filters=["stop_gained"]):
    """
    Fetches mutation data for a gene from Ensembl and applies filters for each mutation type separately.
    Each mutation type gets its own limit.
    """
    # Assuming get_gene_info_ensembl is defined elsewhere to fetch gene info.
    gene_info = get_gene_info_ensembl(gene_name)

    if gene_info:
        gene_id = gene_info["Gene ID"]
        print(f"Fetching mutations for Gene ID: {gene_id}")

        url = f"https://rest.ensembl.org/overlap/id/{gene_id}?feature=variation;content-type=application/json"

        response = requests.get(url)

        if response.status_code == 200:
            mutation_data = response.json()
            print(f"Received {len(mutation_data)} mutations from Ensembl.")

            mutations = []
            seen_variants = set()  # Track unique variants
            count_per_mutation_type = {mt: 0 for mt in mutation_type_filters}  # Keep count of each mutation type

            # Iterate through each mutation in the response
            for mutation in mutation_data:
                variation_id = mutation.get("id", "N/A")
                # If this variation has already been processed, skip it
                if variation_id in seen_variants:
                    continue

                consequence_type = mutation.get("consequence_type", [])

                # Ensure it's always a list even if the API returns a single consequence
                if isinstance(consequence_type, str):
                    consequence_type = [consequence_type]

                # **Process each mutation type separately**
                for mt in mutation_type_filters:
                    # Check if the current mutation type (mt) exists in the mutation's consequence
                    if any(mt.lower() in consequence.lower() for consequence in consequence_type):
                        # Ensure we don't exceed the mutation limit for this mutation type
                        if count_per_mutation_type[mt] >= mutation_limit:
                            continue

                        seq_region_name = mutation.get("seq_region_name", "N/A")
                        allele_string = mutation.get("allele_string", "N/A")

                        if allele_string == "N/A":
                            allele_string = mutation.get("alleles", "N/A")

                        # If allele_string is a list, join them into a string
                        if isinstance(allele_string, list):
                            allele_string = ', '.join(allele_string)

                        # Create a dictionary for this mutation
                        mutation_dict = {
                            "Variation": variation_id,
                            "Location": seq_region_name,
                            "Allele": allele_string,
                            "Consequence": '/'.join(consequence_type),
                        }
                        mutations.append(mutation_dict)

                        # Mark this variation as seen
                        seen_variants.add(variation_id)

                        # Increment the count for this mutation type
                        count_per_mutation_type[mt] += 1

                # Stop processing once we reach the desired limit for all types
                if all(count >= mutation_limit for count in count_per_mutation_type.values()):
                    break

            # Print how many mutations were found for each type
            for mt in mutation_type_filters:
                print(f"Found {count_per_mutation_type[mt]} mutations for {mt}.")

            print(f"Total filtered mutations: {len(mutations)}")

            # Return mutations if found, else return a message
            return mutations if mutations else "No mutations found that match the criteria."
        else:
            print(f"Error fetching mutation data from Ensembl for gene ID: {gene_id}, status code: {response.status_code}")
            return "Error fetching mutation data from Ensembl."
    else:
        print(f"Gene information not found for {gene_name}")
        return "Gene information not found."


def chatbot_with_groq(question, context):
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful genetic counseling assistant."},
            {"role": "user", "content": question},
            {"role": "system", "content": f"Context: {context}"}
        ],
        model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content


def wrap_text(text, width, font_size, font_name="Helvetica", x_offset=100):
    """
    Wrap the text to fit within the given width and adjust for right padding.
    """
    c = canvas.Canvas(BytesIO(), pagesize=letter)
    c.setFont(font_name, font_size)
    words = text.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + " " + word if current_line else word
        text_width = c.stringWidth(test_line, font_name, font_size)
        if text_width <= width - x_offset - 100:  # Adjusted for more right padding
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines
    
def draw_underline(c, text, x_position, y_position, font_name="Helvetica-Bold", font_size=12, x_offset=100, line_padding=0):
    """
    Draw an underline beneath the text at the given position with more padding from the right.
    """
    text_width = c.stringWidth(text, font_name, font_size)
    c.drawString(x_position, y_position, text)
    c.line(x_position, y_position - 2, x_position + text_width + line_padding, y_position - 2)

def draw_full_line(c, y_position, width=500, x_offset=100, line_padding=0):
    """
    Draw a full-width horizontal line to separate gene sections with more right padding.
    """
    c.setStrokeColorRGB(0, 0, 0)  # Black color for the line
    c.setLineWidth(1)
    c.line(x_offset, y_position, x_offset + width + line_padding, y_position)  # Added padding

def generate_report(genes_data):
    """
    Generate a combined PDF report for multiple genes with improved formatting and page handling.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 14)

    # Adjusted margins for header, footer, and more right padding
    header_height = 50  # Space for header at the top
    footer_height = 40  # Space for footer at the bottom
    content_top_margin = 80  # Distance from the top to start content
    content_bottom_margin = footer_height + 20  # Distance from the bottom to leave space for footer
    x_offset = 120  # Increased x_offset for more right padding

    y_position = height - header_height - 20

    # Set the title color to a distinct shade
    c.setFillColorRGB(0.2, 0.4, 0.6)  # Light blue color for the title
    c.drawString(x_offset, y_position, "Genetic Counseling Report")
    y_position -= 30  # Space below header

    def check_page_break(y_position):
        """Check if the current y_position is too low and a page break is needed"""
        if y_position < content_bottom_margin:
            c.showPage()
            c.setFont("Helvetica", 14)  # Reset font for title after page break
            c.setFillColorRGB(0.2, 0.4, 0.6)  # Ensure title color persists
            y_position = height - header_height - 20  # Reset to top of the page with margin
            c.drawString(x_offset, y_position, "Genetic Counseling Report")  # Re-add the title after page break
            y_position -= 30  # Space below title after page break

            c.setFont("Helvetica", 10)  # Reset font for content
        return y_position

    for gene_data in genes_data:
        gene_info, gene_function, mutations = gene_data

        # Gene information header with underline and bold font
        c.setFont("Helvetica-Bold", 12)
        draw_underline(c, f"Gene Information: {gene_info.get('Gene Symbol', 'N/A')}", x_offset, y_position, x_offset=x_offset)
        y_position -= 30

        y_position = check_page_break(y_position)  # Check for page break after header

        c.setFont("Helvetica", 10)
        # Gene information section
        if gene_info:
            for key, value in gene_info.items():
                lines = wrap_text(f"{key}: {value}", width, 10, x_offset=x_offset)
                for line in lines:
                    y_position = check_page_break(y_position)  # Check for page break
                    c.drawString(x_offset, y_position, line)
                    y_position -= 15
        else:
            c.drawString(x_offset, y_position, "No gene information available.")
            y_position -= 20

        y_position -= 20

        # Gene function header with underline and bold font
        c.setFont("Helvetica-Bold", 12)
        draw_underline(c, "Gene Function:", x_offset, y_position, x_offset=x_offset)
        y_position -= 30
        y_position = check_page_break(y_position)  # Check for page break after header
        c.setFont("Helvetica", 10)

        # Gene function section
        if gene_function:
            lines = wrap_text(f"Name: {gene_function['name']}", width, 10, x_offset=x_offset)
            for line in lines:
                y_position = check_page_break(y_position)
                c.drawString(x_offset, y_position, line)
                y_position -= 15

            lines = wrap_text(f"Symbol: {gene_function['symbol']}", width, 10, x_offset=x_offset)
            for line in lines:
                y_position = check_page_break(y_position)
                c.drawString(x_offset, y_position, line)
                y_position -= 15

            lines = wrap_text(f"Function Summary: {gene_function['summary']}", width, 10, x_offset=x_offset)
            for line in lines:
                y_position = check_page_break(y_position)
                c.drawString(x_offset, y_position, line)
                y_position -= 15
        else:
            c.drawString(x_offset, y_position, "No gene function information available.")
            y_position -= 20

        y_position -= 40

        # Mutation header with underline and bold font
        c.setFont("Helvetica-Bold", 12)
        draw_underline(c, "Mutation Interpretation:", x_offset, y_position, x_offset=x_offset)
        y_position -= 30
        y_position = check_page_break(y_position)  # Check for page break after header
        c.setFont("Helvetica", 10)

        # Mutation section
        if mutations:
            for mutation in mutations:
                lines = wrap_text(f"Variation: {mutation['Variation']}", width, 10, x_offset=x_offset)
                for line in lines:
                    y_position = check_page_break(y_position)
                    c.drawString(x_offset, y_position, line)
                    y_position -= 15

                lines = wrap_text(f"Location: {mutation['Location']}", width, 10, x_offset=x_offset)
                for line in lines:
                    y_position = check_page_break(y_position)
                    c.drawString(x_offset, y_position, line)
                    y_position -= 15

                lines = wrap_text(f"Consequence: {mutation['Consequence']}", width, 10, x_offset=x_offset)
                for line in lines:
                    y_position = check_page_break(y_position)
                    c.drawString(x_offset, y_position, line)
                    y_position -= 15

                lines = wrap_text(f"Alleles: {mutation['Allele']}", width, 10, x_offset=x_offset)
                for line in lines:
                    y_position = check_page_break(y_position)
                    c.drawString(x_offset, y_position, line)
                    y_position -= 15

                y_position -= 20
        else:
            c.drawString(x_offset, y_position, "No mutation information available.")
            y_position -= 20

        # Draw a full-width line to separate different genes with extra padding on the right
        y_position -= 40
        draw_full_line(c, y_position, width=500, x_offset=x_offset, line_padding=20)  # Added padding
        y_position -= 40

    # Finalize the PDF
    c.showPage()
    c.save()
    pdf_content = buffer.getvalue()
    buffer.close()
    return pdf_content


# Simulating the same behavior of the get_consequences_from_user function as a streamlit input
def get_consequences_from_user():
    so_terms = [
        "transcript_ablation", "splice_acceptor_variant", "splice_donor_variant", "stop_gained",
        "frameshift_variant", "stop_lost", "start_lost", "transcript_amplification", "feature_elongation",
        "feature_truncation", "inframe_insertion", "inframe_deletion", "missense_variant", "protein_altering_variant",
        "splice_donor_5th_base_variant", "splice_region_variant", "splice_donor_region_variant",
        "splice_polypyrimidine_tract_variant", "incomplete_terminal_codon_variant", "start_retained_variant",
        "stop_retained_variant", "synonymous_variant", "coding_sequence_variant", "mature_miRNA_variant", "5_prime_UTR_variant",
        "3_prime_UTR_variant", "non_coding_transcript_exon_variant", "intron_variant", "NMD_transcript_variant",
        "non_coding_transcript_variant", "coding_transcript_variant", "upstream_gene_variant", "downstream_gene_variant",
        "TFBS_ablation", "TFBS_amplification", "TF_binding_site_variant", "regulatory_region_ablation",
        "regulatory_region_amplification", "regulatory_region_variant", "intergenic_variant"
    ]

    # Streamlit multi-select for mutation consequences
    st.subheader("Select Mutation Consequences")
    consequences_input = st.multiselect("Choose mutation consequences from the list", so_terms)

    return consequences_input


def get_chatbot_response(question, context):
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful genetic counseling assistant."},
            {"role": "user", "content": question},
            {"role": "system", "content": f"Context: {context}"}
        ],
        model="llama3-8b-8192",
    )
    return chat_completion.choices[0].message.content
    

import streamlit as st

# Assuming all necessary functions like `get_gene_info_ensembl()`, `get_gene_function()`, `get_filtered_mutation_data_ensembl()`, `generate_report()` etc. are defined elsewhere.

def genetic_counseling_assistant():
    st.title("Genetic Counseling Assistant")

    # Initialize session state variables
    if 'chatbot_context' not in st.session_state:
        st.session_state.chatbot_context = ""
    
    if 'chatbot_response' not in st.session_state:
        st.session_state.chatbot_response = ""
    
    if 'report_generated' not in st.session_state:
        st.session_state.report_generated = False  # Track whether the report has been generated

    # Direct gene name input
    gene_name = st.text_input("Enter a gene name:", key="gene_name_input_1")

    # Only proceed if the user has entered a gene name
    if gene_name:
        genes = [gene_name]

        # Get mutation limit from user
        mutation_limit = st.number_input("Enter the number of mutations to retrieve (default 5):", min_value=1, value=5, key="mutation_limit_input_1")

        # Get valid mutation consequences from user
        consequences = get_consequences_from_user()

        # Add a button for submitting the mutation consequences
        submit_consequences_button = st.button("Submit Mutation Consequences", key="submit_consequences_button_1")

        genes_data = []

        # Handle button click for submitting consequences
        if submit_consequences_button:
            # Retrieve gene data for all genes
            for gene in genes:
                gene_info = get_gene_info_ensembl(gene)
                gene_function = get_gene_function(gene)
                mutations = get_filtered_mutation_data_ensembl(gene, mutation_limit, consequences)

                genes_data.append((gene_info, gene_function, mutations))

            if genes_data:
                # Display retrieved gene information
                for gene_data in genes_data:
                    gene_info, gene_function, mutations = gene_data
                    st.subheader(f"Gene: {gene_info}")
                    st.write(f"Function: {gene_function}")
                    st.write(f"Mutations: {mutations}")

                # Build complete context for chatbot (hidden from user)
                complete_context = ""
                for gene_data in genes_data:
                    gene_info, gene_function, mutations = gene_data
                    complete_context += f"Gene Information: {gene_info if gene_info else 'None'}\n"
                    complete_context += f"Gene Function: {gene_function if gene_function else 'None'}\n"
                    complete_context += f"Mutation Data: {mutations if mutations else 'None'}\n\n"

                # Save the complete context in session state for chatbot
                st.session_state.chatbot_context = complete_context

                # Only show the "Generate Genetic Counseling Report" button if the report has not been generated yet
                if not st.session_state.report_generated:
                    report_button = st.button("Generate Genetic Counseling Report", key="generate_report_button_1")
                    if report_button:
                        # Generate the report based on the data retrieved
                        report_content = generate_report(genes_data)
                        # Save the generated report as a PDF (using Streamlit's download button)
                        with open("genetic_counseling_report.pdf", "wb") as f:
                            f.write(report_content)

                        # Display the download button
                        st.download_button(
                            label="Download Genetic Counseling Report",
                            data=report_content,
                            file_name="genetic_counseling_report.pdf",
                            mime="application/pdf"
                        )

                        # Mark the report as generated
                        st.session_state.report_generated = True

                # Chatbot interaction for follow-up questions
                follow_up_question = st.text_input("Do you have any follow-up questions related to genetic counseling? Enter your question or leave blank to stop:", key="follow_up_question_input_1")

                if follow_up_question:
                    # Call the chatbot function (assuming chatbot_with_groq is defined)
                    response = chatbot_with_groq(follow_up_question, st.session_state.chatbot_context)
                    st.session_state.chatbot_response = response

                if st.session_state.chatbot_response:
                    st.write(f"Chatbot Response: {st.session_state.chatbot_response}")

        else:
            st.write("Please select and submit mutation consequences to proceed.")

        # Ask if the user wants to process another set of gene data
        continue_session = st.radio("Would you like to process another set of gene data?", ("Yes", "No"), key="continue_session_radio_1")
        if continue_session == "No":
            st.write("Goodbye!")
        elif continue_session == "Yes":
            # Reset report generation state for new session
            st.session_state.report_generated = False  # Allow report generation again if the user chooses to start a new session


# Run the Streamlit app
if __name__ == "__main__":
    genetic_counseling_assistant()
