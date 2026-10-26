"""Independent read-only checks of final figure tables against the locked analysis.

Run after generating all nine figures. No inputs, plots or scores are modified.
"""
from pathlib import Path
import importlib.util
import json
import sqlite3
import sys
from collections import Counter
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / '_shared'))
from current import verify_sources, sha


def close(actual, expected, label):
    a = np.asarray(actual, dtype=float)
    b = np.asarray(expected, dtype=float)
    assert a.shape == b.shape and np.allclose(a, b, atol=1e-9, rtol=1e-9, equal_nan=True), label


def table(fig, name):
    return pd.read_csv(HERE / fig / 'output/source_data' / (name + '.csv'))


def keyed(fig, name, expected):
    result = table(fig, name).set_index('Inchikey_std').sort_index()
    assert result.index.equals(expected.index), (fig, name, 'population')
    for column in result.columns.intersection(expected.columns):
        if column.endswith('_score'):
            close(result[column], pd.to_numeric(expected[column]), (fig, column, 'values and missing pattern'))
        elif column in ['Priority_tier', 'GIC_regulatory_status']:
            assert result[column].equals(expected[column]), (fig, column)
    return result


def main():
    lock = verify_sources()
    db = sqlite3.connect((ROOT / lock['files']['analysis']['path']).as_uri() + '?mode=ro', uri=True)
    full = pd.read_sql_query('SELECT * FROM compounds ORDER BY inchikey', db).set_index('inchikey')
    full.index.name = 'Inchikey_std'
    fields = ['Persistence_score','Bioaccumulation_score','Mobility_score','Toxicity_score',
              'Exposure_food_contact_score','Exposure_human_biomonitoring_score','Exposure_inventory_score',
              'Exposure_production_score','Exposure_patent_score','Exposure_literature_score',
              'Priority_score','Hazard_score','Exposure_score','Exposure_inventory_listing_count']
    for col in fields: full[col] = pd.to_numeric(full[col].replace('', np.nan), errors='raise')
    publication = pd.read_csv(ROOT / lock['files']['publication']['path']).set_index('inchikey').sort_index()
    assert list(publication.index) == list(full.index)
    for col in fields: close(publication[col], full[col], ('publication pair', col))
    with sqlite3.connect((ROOT / lock['files']['dashboard']['path']).as_uri() + '?mode=ro', uri=True) as dashboard:
        metadata = dict(dashboard.execute('SELECT key,value FROM metadata'))
        assert metadata['run_id'] == lock['run_id']
        assert metadata['csv_sha256'] == lock['files']['publication']['sha256']
        assert int(metadata['row_count']) == len(full)
    ranked = full.loc[full.Ranking_eligible.eq(1)].copy()
    assert len(full) == 15125 and len(ranked) == 4244
    assert full.Priority_score.isna().equals(full.Priority_tier.eq('Insufficient evidence'))
    assert ranked[fields].notna().all().all()
    assert (full.priority_result_role == 'analysis_after_eligibility_audit').all()
    assert (full.pm_result_role == 'analysis_after_identity_isolation').all()
    assert (full.bt_result_role == 'analysis_after_identity_isolation').all()
    specs = json.loads((HERE / 'Fig4/figure.yml').read_text())['components']
    contrib = pd.DataFrame({s['component']:ranked[s['score_column']] * s['multiplier'] for s in specs})
    H = ranked.Hazard_score; E = ranked.Exposure_score; S = ranked.Priority_score
    close(H, contrib.iloc[:,:4].sum(axis=1), 'hazard weights')
    close(E, contrib.iloc[:,4:].sum(axis=1), 'exposure sum')
    close(S, H+E, 'total sum')
    def tiers(h,e,high=12):
        return np.where((h+e>=high)&(h>=4)&(e>=4),'High priority',np.where((h+e>=6)&(h>=2)&(e>=2),'Moderate priority','Low priority'))
    assert np.array_equal(tiers(H,E),ranked.Priority_tier)
    basehigh = ranked.Priority_tier.eq('High priority').to_numpy()
    def metrics(h,e,high=12):
        t=tiers(h,e,high); selected=t=='High priority'
        return {'rank_spearman':S.rank().corr((h+e).rank()), 'tier_agreement':np.mean(t==ranked.Priority_tier),
                'high_priority_retention':selected[basehigh].mean(), 'high_priority_jaccard':np.sum(basehigh&selected)/np.sum(basehigh|selected)}
    scenarios={'baseline':(H,E),'equal_pbmt_weights':(2*ranked[fields[:4]].sum(axis=1),E),
               'inventory_linear':(H,E-ranked.Exposure_inventory_score+np.minimum(.5*ranked.Exposure_inventory_listing_count,2)),
               'inventory_halved':(H,E-.5*ranked.Exposure_inventory_score),'exposure_capped':(H,np.minimum(E,8)),
               'high_threshold_11':(H,E),'high_threshold_13':(H,E)}
    # Fig. 1 is a schematic: its population labels must come from the analysis.
    pop=table('Fig1','priority_population').set_index('Priority_tier')['n'].to_dict()
    assert pop==full.Priority_tier.value_counts().to_dict()
    assert table('Fig1','qsar_eligibility').set_index('keep_for_vega')['n'].to_dict()=={True:11236,False:3889}
    # Fig. 2: compare every candidate, including nulls, to the JSON evidence.
    pairs=table('Fig2','compound_comparison')
    paths={'toxicity':('Toxicity_evidence','$.qsar_toxicity.selected.score','$.final_selection.selected.score'),
           'bioaccumulation':('Bioaccumulation_evidence','$.final_selection.independent_candidate.score','$.final_selection.selected.score'),
           'mobility':('Mobility_evidence','$.final_mobility.independent_score','$.final_mobility.score'),
           'persistence':('Persistence_evidence','$.final_selection.independent_candidate.score','$.final_selection.selected.score')}
    for dimension,(field,ind,final) in paths.items():
        expected=pd.read_sql_query(f"SELECT inchikey, json_extract({field}, ?) AS computational_score, json_extract({field}, '$.curated_db.selected.score') AS plastchem_score, json_extract({field}, ?) AS selected_final_score FROM compounds ORDER BY inchikey",db,params=[ind,final]).set_index('inchikey')
        observed=pairs[pairs.dimension_id==dimension].set_index('Inchikey_std').sort_index()
        assert list(observed.index)==list(expected.index)
        for col in expected: close(observed[col],expected[col],('Fig2',dimension,col))
    assert len(pairs)==4*len(full)
    # Fig. 3: all compound values and missing positions, plus denominators.
    keyed('Fig3','compound_values',full)
    assert table('Fig3','priority_score_distribution/priority_distribution').compound_count.sum()==len(ranked)
    for name in ['hazard_component_profiles/hazard_component_profiles','exposure_component_profiles/exposure_indicator_profiles']:
        profiles=table('Fig3',name)
        assert profiles.groupby('component').compound_count.sum().eq(len(full)).all()
        mapping={'Persistence':'Persistence_score','Bioaccumulation':'Bioaccumulation_score','Mobility':'Mobility_score','Toxicity':'Toxicity_score','Inventory presence':'Exposure_inventory_score','Production / market':'Exposure_production_score','Patents':'Exposure_patent_score','Literature':'Exposure_literature_score','Food-contact migration':'Exposure_food_contact_score','Human biomonitoring':'Exposure_human_biomonitoring_score'}
        for component,col in mapping.items():
            rows=profiles[profiles.component==component]
            if len(rows): assert rows.loc[rows.score_class=='No usable evidence','compound_count'].sum()==full[col].isna().sum(), component
    # Fig. 4 and ED3: same observed complete inputs; independently recompute perturbations.
    for fig in ['Fig4','ExtendedDataFig3']:
        observed=keyed(fig,'compound_input_summary',ranked)
        close(observed[contrib.columns],contrib,fig+' contributions')
        close(observed.positive_input_count,(contrib>0).sum(axis=1),fig+' positive count')
    for _,row in table('Fig4','leave_one_input_out/leave_one_input_out').iterrows():
        removal=contrib[row.component]; h=H-removal if row.family=='Hazard' else H; e=E-removal if row.family=='Exposure' else E
        for k,v in metrics(h,e).items(): close(row[k],v,('Fig4 LOO',row.component,k))
    for _,row in table('Fig4','scenario_sensitivity/scenario_sensitivity').iterrows():
        for k,v in metrics(*scenarios[row.scenario_id],high=row.high_threshold).items(): close(row[k],v,('Fig4 scenario',row.scenario_id,k))
    # Fig. 5: endpoint, stability, capture and screening denominators.
    policy=json.loads((HERE/'Fig5/figure.yml').read_text())
    observed=keyed('Fig5','compound_policy_analysis',ranked)
    strong=ranked.GIC_regulatory_status.isin(policy['strong_action_statuses'])
    assert np.array_equal(observed.strong_action,strong)
    stable=tiers(H,E,13)=='High priority'
    for name in ['equal_pbmt_weights','inventory_linear','inventory_halved','exposure_capped']: stable &= tiers(*scenarios[name])=='High priority'
    assert np.array_equal(observed.stable_high_priority,stable)
    assert set(table('Fig5','review_candidates_outside_strong_action').Inchikey_std)==set(ranked.index[stable&~strong])
    for _,row in table('Fig5','strong_action_prevalence/strong_action_prevalence').iterrows():
        sel=ranked.Priority_tier.eq(row.priority_tier)
        close(row.compound_count,sel.sum(),'Fig5 tier n');close(row.strong_action_count,strong[sel].sum(),'Fig5 endpoint n')
        close(row.proportion,strong[sel].mean(),'Fig5 prevalence')
    methods={'Integrated score':S,'Integrated, inventory removed':S-ranked.Exposure_inventory_score,'Exposure only':E,'Hazard only':H}
    for _,row in table('Fig5','ranking_capture/ranking_capture_markers').iterrows():
        grouped=pd.DataFrame({'score':methods[row.method],'endpoint':strong.astype(int)}).groupby('score').endpoint.agg(['sum','count']).sort_index(ascending=False)
        x=np.r_[0,grouped['count'].cumsum()/len(ranked)];y=np.r_[0,grouped['sum'].cumsum()/strong.sum()]
        close(row.screened_fraction,basehigh.mean(),'Fig5 screen fraction')
        close(row.captured_fraction,np.interp(basehigh.mean(),x,y),'Fig5 tie-aware capture')
    # ED1: source membership is a relation, independent of scoring nulls.
    source_map={r:({'fcchumon_s1':'FCChumon_S1','fcchumon_s2':'FCChumon_S2'}.get(t,s)) for r,s,t in db.execute('SELECT record_id,source_id,table_id FROM source_records')}
    expected={(k,source_map[r]) for k,r in db.execute('SELECT inchikey,record_id FROM compound_memberships')}
    observed=table('ExtendedDataFig1','memberships')
    assert set(zip(observed.inchikey_std,observed.source_id))==expected
    assert table('ExtendedDataFig1','record_flow').record_count.sum()==len(source_map)
    inter=table('ExtendedDataFig1','overlap/intersections');assert inter.compound_count.sum()==len(full)
    selected=table('ExtendedDataFig1','overlap/selected');assert selected.compound_count.ge(100).all() and selected.compound_count.sum()==13221
    spec=importlib.util.spec_from_file_location('alignment',HERE/'ExtendedDataFig1/audit_alignment.py');alignment=importlib.util.module_from_spec(spec);spec.loader.exec_module(alignment)
    alignment_result=alignment.check()
    # ED2: presence of hazard evidence includes genuine zero; positive exposure requires all six observed inputs.
    observed=keyed('ExtendedDataFig2','hazard/membership',full)
    for col in fields[:4]: assert np.array_equal(observed[col[:-6]],full[col].notna()),col
    exposure=full.loc[full.Exposure_complete.eq('True')];assert len(exposure)==7951
    observed=keyed('ExtendedDataFig2','exposure/membership',exposure)
    for label,col in [('Inventory presence','Exposure_inventory_score'),('Production / market','Exposure_production_score'),('Patents','Exposure_patent_score'),('Literature','Exposure_literature_score')]:
        assert np.array_equal(observed[label],exposure[col]>0),label
    assert np.array_equal(observed['Food-contact + biomonitoring'],exposure[['Exposure_food_contact_score','Exposure_human_biomonitoring_score']].sum(axis=1)>0)
    for _,row in table('ExtendedDataFig3','positive_input_prevalence/positive_input_prevalence').iterrows():
        sel=ranked.Priority_tier.eq(row.priority_tier);close(row.positive_compounds,(contrib.loc[sel,row.component]>0).sum(),'ED3 prevalence')
    # ED4: real loaded detail view, with no placeholder evidence or demo labels.
    text=(HERE/'ExtendedDataFig4/output/source_data/visible_text.txt').read_text()
    for token in ['WHHGLZMJPXIBIX-UHFFFAOYSA-N','655','GC-EI-MS','Carcinogenicity_CAESAR']: assert token in text
    for token in ['Evidence not loaded','Details not loaded','(Demo)']: assert token not in text
    example=full.loc['WHHGLZMJPXIBIX-UHFFFAOYSA-N'];close([example.Priority_score,example.Hazard_score,example.Exposure_score,example.Exposure_literature_count],[26,16,10,655],'ED4 example')
    # Verify every figure's file and code lineage. Reject stale renders.
    figures=[f'Fig{i}' for i in range(1,6)]+[f'ExtendedDataFig{i}' for i in range(1,5)]
    for fig in figures:
        manifest=json.loads((HERE/fig/'output/manifest.json').read_text());assert manifest['source']==lock
        for path,digest in manifest['code'].items(): assert sha(ROOT/path)==digest,('stale code',fig,path)
        for path,digest in manifest['outputs'].items(): assert sha(HERE/fig/'output'/path)==digest,('stale output',fig,path)
    return {'passed':True,'run_id':lock['run_id'],'figures':figures,'population':len(full),'ranked':len(ranked),'insufficient':len(full)-len(ranked),'exposure_complete':len(exposure),'missing_policy':'Values and null masks checked against current canonical analysis; no score imputation.','upset_alignment':alignment_result,'limits':'Confirms the locked analysis and figure derivations; does not revalidate external databases or rerun third-party QSAR models.'}

if __name__=='__main__':
    result=main();print(json.dumps(result,indent=2))
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
