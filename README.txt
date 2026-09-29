RODOKMEN – interaktivní aplikace

1. Nainstaluj Python 3.
2. V PowerShellu přejdi do této složky.
3. Nainstaluj balíčky:
   python -m pip install -r requirements.txt
4. Spusť:
   python -m streamlit run app.py

Aplikace používá rodokmen.ods jako výběr osob a rodokmen.ged jako zdroj doplňujících údajů a rodinných vazeb.
V prohlížeči lze celý strom přibližovat kolečkem, posouvat tažením a kliknutím zobrazit detail osoby.

Poznámka: ODS obsahuje 336 osobních záznamů a 313 různých textových jmen. Duplicitní jména jsou ponechána jako samostatné záznamy, aby se nesloučili různí lidé se stejným jménem.
