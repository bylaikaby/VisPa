"""Version: 0.1.2 (local/unreleased)
Last updated: 2026-11-18
Change history: ../CHANGELOG.md
- 2026-11-18: Check aligned projection distribution and invalid input guards.
- 2026-11-18: Check style rendering, order preservation, and threshold/length validation.
- 2026-11-18: Verify projection alignment, full normalization and render protection.
"""
import unittest
import numpy as np
import pandas as pd
from pathlib import Path
from tests.local_temp import local_temp
from remap.morph_clustering.review_plot import prepare_projection, render_review, render_alternative, render_projection_distribution
from remap.morph_clustering.review_profile import fit_profile

class ReviewProfileTests(unittest.TestCase):
    def test_projection_distribution(self):
        with local_temp() as folder:
            path=Path(folder)/"distribution.png"
            p={"plots":{"dpi":72},"clustering":{"display_k":2}}
            values=np.array([[.6,.2],[.2,.3],[0,.5]])
            result=render_projection_distribution([1,1,2],list("abc"),values,["region"],p,path,top_regions=1,total_regions=3)
            self.assertTrue(path.exists()); self.assertEqual(result["cluster_counts"],{"1":2,"2":1}); self.assertTrue(result["points_include_zero"])
            with self.assertRaises(ValueError):
                render_projection_distribution([1,1,2],list("abc"),values,["region"],p,Path(folder)/"bad.png",top_regions=2)
            with self.assertRaises(ValueError):
                render_projection_distribution([1,1,2],["a","a","c"],values,["region"],p,Path(folder)/"duplicate.png",top_regions=1)

    def test_alternative_styles_and_validation(self):
        raw=np.array([[0,1,4,5],[1,0,5,4],[4,5,0,1],[5,4,1,0.]])
        profile={"clustering":{"candidate_k":[2],"display_k":2,"representation":"spearman_profile","linkage":"ward_d2","penalty_factor":.5},
                 "comparators":{"penalty_factors":[.5]},"plots":{"type_palette":{"ITi":"blue","ITs":"orange"},"animal_palette":{"A":"green","B":"purple"},"dpi":72}}
        types=["ITi","ITi","ITs","ITs"]; animals=["A","B","A","B"]; identities=list("abcd")
        projection=np.array([[.8,.1,.1,0],[.7,.2,.1,0],[.1,.4,.1,.4],[0,.5,0,.5]])
        fit=fit_profile(raw,types,profile)[.5]
        with local_temp() as folder:
            orders=[]
            for style in ("neuron_projection","distance_matrix","cluster_summary"):
                output=Path(folder)/(style+".png")
                result=render_alternative(fit,types,animals,identities,projection,["A","B"],profile,output,style,projection_lengths=projection*100,total_regions=2)
                self.assertTrue(output.is_file()); orders.append(result["order"])
                self.assertEqual(sum(result["cluster_counts"].values()),4)
            self.assertEqual(orders[0],orders[1]); self.assertEqual(orders[0],orders[2])
            with self.assertRaises(ValueError):
                render_alternative(fit,types,animals,identities,projection,["A","B"],profile,Path(folder)/"invalid.png","cluster_summary",prevalence_threshold=1.1)
            with self.assertRaises(ValueError):
                render_alternative(fit,types,animals,identities,projection,["A","B"],profile,Path(folder)/"missing.png","neuron_projection")

    def test_alignment_and_full_denominator(self):
        ipsi = pd.DataFrame({"A":[3.,1.],"B":[1.,3.]}, index=["b","a"])
        contra = pd.DataFrame({"A":[0.,4.],"B":[4.,0.]}, index=["a","b"])
        shown, regions, all_values = prepare_projection(ipsi,contra,["a","b"],1)
        np.testing.assert_allclose(all_values.sum(axis=1),1)
        np.testing.assert_allclose(all_values[0],[.125,.375,0,.5])
        self.assertTrue(np.all(shown.sum(axis=1)<1))
        with self.assertRaises(ValueError):prepare_projection(ipsi,contra,["absent"],1)
        with self.assertRaises(ValueError):prepare_projection(ipsi,contra,["a","b"],3)
        with self.assertRaises(ValueError):prepare_projection(ipsi*0,contra*0,["a","b"],1)
        ipsi.loc["a","A"]=np.nan
        with self.assertRaises(ValueError):prepare_projection(ipsi,contra,["a","b"],1)

    def test_render_and_no_overwrite(self):
        from PIL import Image
        raw=np.array([[0,1,4,5],[1,0,5,4],[4,5,0,1],[5,4,1,0.]])
        profile={"clustering":{"candidate_k":[2],"display_k":2,"representation":"spearman_profile","linkage":"ward_d2","penalty_factor":1.5},
                 "comparators":{"penalty_factors":[0,1.5]},
                 "plots":{"type_palette":{"ITi":"blue","ITs":"orange"},"projection_level":"L3","dpi":72}}
        types=["ITi","ITi","ITs","ITs"]
        fits=fit_profile(raw,types,profile)
        with local_temp() as folder:
            output=Path(folder)/"plot.png"
            orders=render_review(fits,types,list("abcd"),np.array([[.8,.1,.1,0],[.7,.2,.1,0],[.1,.4,.1,.4],[0,.5,0,.5]]),["A","B"],profile,output,"Test")
            with Image.open(output) as im:self.assertGreater(im.width,500)
            self.assertEqual(set(orders["0"]),set("abcd"))
            original=output.read_bytes()
            with self.assertRaises(FileExistsError):render_review(fits,types,list("abcd"),np.zeros((4,4)),["A","B"],profile,output,"Test")
            self.assertEqual(output.read_bytes(),original)

if __name__=="__main__":unittest.main()
