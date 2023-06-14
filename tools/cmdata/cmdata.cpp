/*
 * This file is part of the GROMACS molecular simulation package.
 *
 * Copyright 2010- The GROMACS Authors
 * and the project initiators Erik Lindahl, Berk Hess and David van der Spoel.
 * Consult the AUTHORS/COPYING files and https://www.gromacs.org for details.
 *
 * GROMACS is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public License
 * as published by the Free Software Foundation; either version 2.1
 * of the License, or (at your option) any later version.
 *
 * GROMACS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with GROMACS; if not, see
 * https://www.gnu.org/licenses, or write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA.
 *
 * If you want to redistribute modifications to GROMACS, please
 * consider that scientific software is very special. Version
 * control is crucial - bugs must be traceable. We will be happy to
 * consider code for inclusion in the official distribution, but
 * derived work must not be called official GROMACS. Details are found
 * in the README & COPYING files - if they are missing, get the
 * official version at https://www.gromacs.org.
 *
 * To help us fund GROMACS development, we humbly ask that you cite
 * the research papers on the package. Check out https://www.gromacs.org.
 */
/*! \internal \file
 * \brief
 * Implements gmx::analysismodules::CMData.
 *
 * \author multi-eGO development team
 * \ingroup module_trajectoryanalysis
 */
#include "gmxpre.h"

#include "cmdata.h"

#include "gromacs/analysisdata/analysisdata.h"
#include "gromacs/options/basicoptions.h"
#include "gromacs/options/filenameoption.h"
#include "gromacs/options/ioptionscontainer.h"
#include "gromacs/selection/selection.h"
#include "gromacs/selection/selectionoption.h"
#include "gromacs/trajectory/trajectoryframe.h"
#include "gromacs/trajectoryanalysis/analysissettings.h"
#include "gromacs/trajectoryanalysis/topologyinformation.h"
#include "gromacs/math/vec.h"
#include "gromacs/pbcutil/pbc.h"
#include "gromacs/fileio/tpxio.h"
#include "gromacs/fileio/trxio.h"
#include "gromacs/topology/mtop_lookup.h"
#include "gromacs/topology/mtop_util.h"
#include "gromacs/utility/futil.h"
#include "gromacs/utility/gmxassert.h"
#include "gromacs/utility/smalloc.h"

#include <cmath>
#include <memory>
#include <string>
#include <algorithm>
#include <functional>
#include <numeric>

namespace gmx
{
 
namespace analysismodules
{
 
namespace
{

class CMData : public TrajectoryAnalysisModule
{
public:
  CMData();

  void initOptions(IOptionsContainer *options, TrajectoryAnalysisSettings *settings) override;
  void initAnalysis(const TrajectoryAnalysisSettings &settings, const TopologyInformation &top) override;

  void analyzeFrame(int frnr, const t_trxframe &fr, t_pbc *pbc, TrajectoryAnalysisModuleData *pdata) override;

  void finishAnalysis(int nframes) override;
  void writeOutput() override;

private:
  Selection refsel_;
  bool histo_;
  double cutoff_;
  double mol_cutoff_;
  int n_x_;
  int nframe_;
  rvec *xcm_ = nullptr;
  gmx_mtop_t *mtop_;
  std::vector<int> mol_id_;
  std::string outfile_inter_;
  std::string outfile_intra_;
  std::vector<double> inv_num_mol_;

  std::vector<int> natmol2_;
  int nindex_;
  gmx::RangePartitioning mols_;
  std::vector<std::vector<int>> cross_index_;
  std::vector<t_atoms> molecules_;
  const char *atomname_;
  std::vector<double> density_bins_;

  double mcut2_;
  double cut_sig_2_;
  std::vector<std::vector<std::vector<std::vector<double>>>> interm_same_mat_density_;
  std::vector<std::vector<std::vector<std::vector<double>>>> interm_cross_mat_density_;
  std::vector<std::vector<std::vector<std::vector<double>>>> intram_mat_density_;
};

CMData::CMData() : histo_(false),
                   outfile_intra_(""),
                   outfile_inter_("") {}

void CMData::initOptions(IOptionsContainer *options, TrajectoryAnalysisSettings *settings)
{
  static const char *const desc[] = {
      "[THISMODULE] calculates the intra- and intermat properties for multi-eGO",
  };

  settings->setHelpText(desc);

  options->addOption(DoubleOption("cutoff")
                         .store(&cutoff_)
                         .defaultValue(0.75)
                         .description("Cutoff in which to consider contacts"));
  options->addOption(DoubleOption("mol_cutoff")
                         .store(&mol_cutoff_)
                         .defaultValue(6.0)
                         .description("Molecular cutoff in which to consider contacts intermolecularly"));
  options->addOption(FileNameOption("intra")
                         .store(&outfile_intra_)
                         .description("Output of the intra-molecular contacts"));
  options->addOption(FileNameOption("inter")
                         .store(&outfile_inter_)
                         .description("Output of the intra-molecular contacts"));
  options->addOption(BooleanOption("histo")
                         .store(&histo_)
                         .description("Set to true to output histograms"));
  options->addOption(SelectionOption("reference")
                         .store(&refsel_)
                         .required()
                         .dynamicMask()
                         .description("Groups to calculate distances to"));

  // always require topology
  settings->setFlag(TrajectoryAnalysisSettings::efRequireTop);
}

static inline void kernel_density_estimator(std::vector<double> &x, const std::vector<double> &bins, const double mu, const double norm)
{
  double h = 0.01;
  double from_x = std::max(mu - 2 * h, bins[0]);
  double to_x = std::min(mu + 2 * h, bins.back());
  auto is_geq_start = [&from_x](double i) { return i >= from_x; };
  auto is_geq_end = [&to_x](double i) { return i > to_x; };
  auto start = std::find_if(bins.begin(), bins.end(), is_geq_start);
  auto end = std::find_if(bins.begin(), bins.end(), is_geq_end);
  int from = std::distance(bins.begin(), start);
  int to = std::distance(bins.begin(), end);
  double scale = norm / (0.73853587 * h * std::sqrt(2. * M_PI));
  if (mu < h) scale *= 2.;
  double shift = std::exp(-2.);
  for (int i = from; i < to; i++)
  {
    double f = (mu - bins[i]) / h;
    double kernel = std::exp(-0.5 * f * f);
    x[i] += scale * (kernel - shift);
  }
}

static inline double calc_mean(const std::vector<double> &v, const double dx)
{
  double dm = 0.;
  double norm = 0.;
  for (auto it = v.begin(); it != v.end(); ++it)
  {
    unsigned i = std::distance(v.begin(), it);
    if (v[i] > 0.)
    {
      double d = (dx * static_cast<double>(i) + 0.5 * dx);
      dm += v[i] * d;
      norm += v[i];
    }
  }
  if (norm == 0.) norm = 1.;
  return dm / norm;
}

static inline double calc_prob(const std::vector<double> &v, const double dx)
{
  double prob = 0.;
  for (auto it = v.begin(); it != v.end(); ++it)
  {
    unsigned i = std::distance(v.begin(), it);
    if (v[i] > 0.) prob += v[i] * dx;
  }
  if (prob > 1.) prob = 1.;
  return prob;
}

static inline int n_bins(const double cut, const double factor = 4.0)
{
  return cut / (0.01 / factor);
}

void CMData::initAnalysis(const TrajectoryAnalysisSettings &settings, const TopologyInformation &top)
{
  if (outfile_inter_ == "") outfile_inter_ = std::string("intermat.ndx");
  if (outfile_intra_ == "") outfile_intra_ = std::string("intramat.ndx");
  n_x_ = 0;
  nframe_ = 0;
  mtop_ = top.mtop();
  mols_ = gmx_mtop_molecules(*top.mtop());

  // number of molecules
  nindex_ = mols_.numBlocks();
  std::vector<int> num_mol;
  num_mol.push_back(1);
  int num_unique_molecules = 0;
  // number of atoms per molecule, assuming them identical when consecutive molecules have the same number of atoms
  natmol2_.push_back(mols_.block(0).end());
  for (int i = 1; i < nindex_; i++)
  {
    natmol2_.push_back(mols_.block(i).end() - mols_.block(i - 1).end());
    if (natmol2_[i] == natmol2_[i - 1]) num_mol[num_unique_molecules]++;
    else
    {
      num_mol.push_back(1);
      num_unique_molecules++;
    }
  }
  std::vector<int>::iterator it = std::unique(natmol2_.begin(), natmol2_.end());
  natmol2_.resize(std::distance(natmol2_.begin(), it));

  std::vector<int> start_index;
  mol_id_.push_back(0);
  start_index.push_back(0);
  num_unique_molecules = 0;
  inv_num_mol_.push_back(1. / (static_cast<double>(num_mol[num_unique_molecules])));

  for (int i = 1; i < nindex_; i++)
  {
    if (mols_.block(i).end() - mols_.block(i - 1).end() == natmol2_[num_unique_molecules])
    {
      start_index.push_back(start_index[i - 1]);
    }
    else
    {
      start_index.push_back(natmol2_[num_unique_molecules]);
      num_unique_molecules++;
    }
    mol_id_.push_back(num_unique_molecules);
    inv_num_mol_.push_back(1. / static_cast<double>(num_mol[num_unique_molecules]));
  }

  printf("number of different molecules %lu\n", natmol2_.size());

  interm_same_mat_density_.resize(natmol2_.size());
  interm_cross_mat_density_.resize((natmol2_.size() * (natmol2_.size() - 1)) / 2);
  intram_mat_density_.resize(natmol2_.size());

  density_bins_.resize(n_bins(cutoff_));
  for (int i = 0; i < density_bins_.size(); i++)
    density_bins_[i] = cutoff_ / static_cast<double>(density_bins_.size()) * static_cast<double>(i) + cutoff_ / static_cast<double>(density_bins_.size() * 2);

  int cross_count = 0;
  cross_index_.resize(natmol2_.size(), std::vector<int>(natmol2_.size(), 0));
  for (std::size_t i = 0; i < natmol2_.size(); i++)
  {
    interm_same_mat_density_[i].resize(natmol2_[i], std::vector<std::vector<double>>(natmol2_[i], std::vector<double>(n_bins(cutoff_), 0)));
    intram_mat_density_[i].resize(natmol2_[i], std::vector<std::vector<double>>(natmol2_[i], std::vector<double>(n_bins(cutoff_), 0)));
    for (std::size_t j = i + 1; j < natmol2_.size(); j++)
    {
      interm_cross_mat_density_[i].resize(natmol2_[i], std::vector<std::vector<double>>(natmol2_[j], std::vector<double>(n_bins(cutoff_), 0)));
      cross_index_[i][j] = cross_count;
      cross_count++;
    }
  }

  mcut2_ = mol_cutoff_ * mol_cutoff_;
  cut_sig_2_ = (cutoff_ + 0.02) * (cutoff_ + 0.02);
  snew(xcm_, nindex_);
}

void CMData::analyzeFrame(int frnr, const t_trxframe &fr, t_pbc *pbc, TrajectoryAnalysisModuleData *pdata)
{
  // WARNING IMPLEMENT
  int nskip = 0;
  // WARNING END

  // WARNING free memory again
  rvec *x = fr.x;

  if ((nskip == 0) || ((nskip > 0) && ((frnr % nskip) == 0)))
  {
    /* calculate the center of each molecule */
    for (int i = 0; (i < nindex_); i++)
    {
      clear_rvec(xcm_[i]);
      double tm = 0.;
      for (int ii = mols_.block(i).begin(); ii < mols_.block(i).end(); ii++)
      {
        for (int m = 0; (m < DIM); m++)
        {
          xcm_[i][m] += x[ii][m];
        }
        tm += 1.0;
      }
      for (int m = 0; (m < DIM); m++)
      {
        xcm_[i][m] /= tm;
      }
    }

    /* Loop over molecules */
    for (int i = 0; i < nindex_; i++)
    {
      int molb = 0;
      // Temporary structures for intermediate values
      // this is to set that at least on interaction has been found
      // for each molecule we want to count an atom pair no more than once, and we consider the pair with the shorter distance
      // matrices atm x atm for accumulating distances
      std::vector<std::vector<double>> interm_same_mat_mdist(natmol2_[mol_id_[i]], std::vector<double>(natmol2_[mol_id_[i]], 100.));
      std::vector<std::vector<double>> intram_mat_mdist(natmol2_[mol_id_[i]], std::vector<double>(natmol2_[mol_id_[i]], 100.));
      std::vector<std::vector<std::vector<double>>> interm_cross_mat_mdist((natmol2_.size() * (natmol2_.size() - 1)) / 2);
      for (std::size_t j = mol_id_[i] + 1; j < natmol2_.size(); j++)
      {
        interm_cross_mat_mdist[cross_index_[mol_id_[i]][j]].resize(natmol2_[mol_id_[i]], std::vector<double>(natmol2_[mol_id_[j]], 100.));
      }
      /* Loop over molecules  */
      for (int j = 0; j < nindex_; j++)
      {
        rvec dx;
        if (j != i)
        {
          if (pbc != nullptr) pbc_dx(pbc, xcm_[i], xcm_[j], dx); // changed
          else rvec_sub(xcm_[i], xcm_[j], dx);
          double dx2 = iprod(dx, dx);
          if (dx2 > mcut2_) continue;
        }
        if (mol_id_[i] != mol_id_[j] && j < i) continue;

        /* Compute distance */
        int a_i = 0;
        GMX_RELEASE_ASSERT(mols_.numBlocks() > 0, "Cannot access index[] from empty mols");
        for (int ii = mols_.block(i).begin(); ii < mols_.block(i).end(); ii++)
        {
          int a_j = 0;
          mtopGetAtomAndResidueName(*mtop_, ii, &molb, &atomname_, nullptr, nullptr, nullptr);
          if (atomname_[0] == 'H')
          {
            a_i++;
            continue;
          }
          for (int jj = mols_.block(j).begin(); jj < mols_.block(j).end(); jj++)
          {
            mtopGetAtomAndResidueName(*mtop_, jj, &molb, &atomname_, nullptr, nullptr, nullptr);
            if (atomname_[0] == 'H')
            {
              a_j++;
              continue;
            }
            if (pbc != nullptr) pbc_dx(pbc, x[ii], x[jj], dx);
            else rvec_sub(x[ii], x[jj], dx);
            double dx2 = iprod(dx, dx);
            double dx3 = 100;
            int delta = a_i - a_j;
            if (i != j && mol_id_[i] == mol_id_[j])
            {
              // this is to account for inversion atom/molecule
              if (pbc != nullptr) pbc_dx(pbc, x[ii - delta], x[jj + delta], dx);
              else rvec_sub(x[ii - delta], x[jj + delta], dx);
              dx3 = iprod(dx, dx);
            }
            if (dx3 < dx2) dx2 = dx3;

            if (dx2 < cut_sig_2_)
            {
              if (i != j)
              { // intermolecular
                if (mol_id_[i] == mol_id_[j])
                { // inter same molecule specie
                  interm_same_mat_mdist[a_i][a_j] = std::min(interm_same_mat_mdist[a_i][a_j], dx2);
                }
                else
                { // inter cross molecule specie
                  interm_cross_mat_mdist[cross_index_[mol_id_[i]][mol_id_[j]]][a_i][a_j] = std::min(interm_cross_mat_mdist[cross_index_[mol_id_[i]][mol_id_[j]]][a_i][a_j], dx2);
                }
              }
              else
              { // intramolecular
                intram_mat_mdist[a_i][a_j] = std::min(intram_mat_mdist[a_i][a_j], dx2);
              }
            }
            a_j++;
          }
          a_i++;
        }
      }
      for (int ii = 0; ii < natmol2_[mol_id_[i]]; ii++)
      {
        for (int jj = ii; jj < natmol2_[mol_id_[i]]; jj++)
        {
          if (interm_same_mat_mdist[ii][jj] < 100.)
          {
            kernel_density_estimator(interm_same_mat_density_[mol_id_[i]][ii][jj], density_bins_, std::sqrt(interm_same_mat_mdist[ii][jj]), inv_num_mol_[i]);
          }
          if (intram_mat_mdist[ii][jj] < 100.)
          {
            kernel_density_estimator(intram_mat_density_[mol_id_[i]][ii][jj], density_bins_, std::sqrt(intram_mat_mdist[ii][jj]), inv_num_mol_[i]);
          }
        }
      }
      for (std::size_t j = mol_id_[i] + 1; j < natmol2_.size(); j++)
      {
        for (int ii = 0; ii < natmol2_[mol_id_[i]]; ii++)
        {
          for (int jj = 0; jj < natmol2_[mol_id_[j]]; jj++)
          {
            if (interm_cross_mat_mdist[cross_index_[mol_id_[i]][j]][ii][jj] < 100.)
            {
              kernel_density_estimator(interm_cross_mat_density_[cross_index_[mol_id_[i]][j]][ii][jj], density_bins_, std::sqrt(interm_cross_mat_mdist[cross_index_[mol_id_[i]][j]][ii][jj]), std::max(inv_num_mol_[i], inv_num_mol_[j]));
            }
          }
        }
      }
    }
    n_x_++;
  }
  nframe_++;
}

void CMData::finishAnalysis(int /*nframes*/)
{
  // normalisations
  double norm = 1. / n_x_;

  for (std::size_t i = 0; i < natmol2_.size(); i++)
  {
    for (int ii = 0; ii < natmol2_[i]; ii++)
    {
      for (int jj = ii; jj < natmol2_[i]; jj++)
      {
        std::transform(interm_same_mat_density_[i][ii][jj].begin(), 
                       interm_same_mat_density_[i][ii][jj].end(), 
                       interm_same_mat_density_[i][ii][jj].begin(), 
                       [&norm](auto &c) { return c * norm; });
        std::transform(intram_mat_density_[i][ii][jj].begin(), 
                       intram_mat_density_[i][ii][jj].end(),
                       intram_mat_density_[i][ii][jj].begin(),
                       [&norm](auto &c) { return c * norm; });
        interm_same_mat_density_[i][jj][ii] = interm_same_mat_density_[i][ii][jj];
        intram_mat_density_[i][jj][ii] = intram_mat_density_[i][ii][jj];
      }
    }
    for (std::size_t j = i + 1; j < natmol2_.size(); j++)
    {
      for (int ii = 0; ii < natmol2_[i]; ii++)
      {
        for (int jj = 0; jj < natmol2_[j]; jj++)
        {
          std::transform(interm_cross_mat_density_[cross_index_[i][j]][ii][jj].begin(),
                         interm_cross_mat_density_[cross_index_[i][j]][ii][jj].end(),
                         interm_cross_mat_density_[cross_index_[i][j]][ii][jj].begin(),
                         [&norm](auto &c) { return c * norm; });
        }
      }
    }
  }
}

void CMData::writeOutput()
{
  if (histo_)
  {
    for (std::size_t i = 0; i < natmol2_.size(); i++)
    {
      for (int ii = 0; ii < natmol2_[i]; ii++)
      {
        FILE *fp_inter = nullptr;
        FILE *fp_intra = nullptr;
        std::string ffh_inter = "inter_mol_" + std::to_string(i + 1) + "_" + std::to_string(i + 1) + "_aa_" + std::to_string(ii + 1) + ".dat";
        fp_inter = gmx_ffopen(ffh_inter, "w");
        std::string ffh_intra = "intra_mol_" + std::to_string(i + 1) + "_" + std::to_string(i + 1) + "_aa_" + std::to_string(ii + 1) + ".dat";
        fp_intra = gmx_ffopen(ffh_intra, "w");
        for (int k = 0; k < interm_same_mat_density_[i][ii][0].size(); k++)
        {
          fprintf(fp_inter, "%lf", density_bins_[k]);
          fprintf(fp_intra, "%lf", density_bins_[k]);
          for (int jj = 0; jj < natmol2_[i]; jj++)
          {
            fprintf(fp_inter, " %lf", interm_same_mat_density_[i][ii][jj][k]);
            fprintf(fp_intra, " %lf", intram_mat_density_[i][ii][jj][k]);
          }
          fprintf(fp_inter, "\n");
          fprintf(fp_intra, "\n");
        }
        gmx_ffclose(fp_inter);
        gmx_ffclose(fp_intra);
      }
      for (std::size_t j = i + 1; j < natmol2_.size(); j++)
      {
        for (int ii = 0; ii < natmol2_[i]; ii++)
        {
          FILE *fp = nullptr;
          std::string ffh = "inter_mol_" + std::to_string(i + 1) + "_" + std::to_string(j + 1) + "_aa_" + std::to_string(ii + 1) + ".dat";
          fp = gmx_ffopen(ffh, "w");
          for (int k = 0; k < interm_cross_mat_density_[cross_index_[i][j]][ii][0].size(); k++)
          {
            fprintf(fp, "%lf", density_bins_[k]);
            for (int jj = 0; jj < natmol2_[j]; jj++)
            {
              fprintf(fp, " %lf", interm_cross_mat_density_[cross_index_[i][j]][ii][jj][k]);
            }
            fprintf(fp, "\n");
          }
          gmx_ffclose(fp);
        }
      }
    }
  }

  for (int i = 0; i < natmol2_.size(); i++)
  {
    FILE *fp = nullptr;
    std::string inter_file_name(outfile_inter_);
    std::size_t found = inter_file_name.find_last_of(".");
    fp = gmx_ffopen(inter_file_name.insert(found, "_" + std::to_string(i + 1) + "_" + std::to_string(i + 1)), "w");
    for (int ii = 0; ii < natmol2_[i]; ii++)
    {
      for (int jj = 0; jj < natmol2_[i]; jj++)
      {
        double dx = cutoff_ / static_cast<double>(interm_same_mat_density_[i][ii][jj].size());
        double dm = calc_mean(interm_same_mat_density_[i][ii][jj], dx);
        double prob = calc_prob(interm_same_mat_density_[i][ii][jj], dx);
        fprintf(fp, "%4i %4i %4i %4i %9.6lf %9.6lf\n", i + 1, ii + 1, i + 1, jj + 1, dm, prob);
      }
    }
    gmx_ffclose(fp);
    std::string intra_file_name(outfile_intra_);
    found = intra_file_name.find_last_of(".");
    fp = gmx_ffopen(intra_file_name.insert(found, "_" + std::to_string(i + 1) + "_" + std::to_string(i + 1)), "w");
    for (int ii = 0; ii < natmol2_[i]; ii++)
    {
      for (int jj = 0; jj < natmol2_[i]; jj++)
      {
        double dx = cutoff_ / static_cast<double>(intram_mat_density_[i][ii][jj].size());
        double dm = calc_mean(intram_mat_density_[i][ii][jj], dx);
        double prob = calc_prob(intram_mat_density_[i][ii][jj], dx);
        fprintf(fp, "%4i %4i %4i %4i %9.6lf %9.6lf\n", i + 1, ii + 1, i + 1, jj + 1, dm, prob);
      }
    }
    gmx_ffclose(fp);
    for (int j = i + 1; j < natmol2_.size(); j++)
    {
      std::string inter_c_file_name(outfile_inter_);
      found = inter_c_file_name.find_last_of(".");
      fp = gmx_ffopen(inter_c_file_name.insert(found, "_" + std::to_string(i + 1) + "_" + std::to_string(j + 1)), "w");
      for (int ii = 0; ii < natmol2_[i]; ii++)
      {
        for (int jj = 0; jj < natmol2_[j]; jj++)
        {
          double dx = cutoff_ / static_cast<double>(interm_cross_mat_density_[cross_index_[i][j]][ii][jj].size());
          double dm = calc_mean(interm_cross_mat_density_[cross_index_[i][j]][ii][jj], dx);
          double prob = calc_prob(interm_cross_mat_density_[cross_index_[i][j]][ii][jj], dx);
          fprintf(fp, "%4i %4i %4i %4i %9.6lf %9.6lf\n", i + 1, ii + 1, j + 1, jj + 1, dm, prob);
        }
      }
      gmx_ffclose(fp);
    }
  }
}

} // namespace

const char CMDataInfo::name[] = "cmdata";
const char CMDataInfo::shortDescription[] = "Calculate contact data";

TrajectoryAnalysisModulePointer CMDataInfo::create()
{
  return TrajectoryAnalysisModulePointer(new CMData);
}

} // namespace analysismodules

} // namespace gmx
