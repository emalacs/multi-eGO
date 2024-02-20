#ifndef _XTC_FRAME_HPP
#define _XTC_FRAME_HPP

#include "gromacs/math/vec.h"
#include "gromacs/math/vectypes.h"

#include <xdrfile_xtc.h>

namespace cmdata::xtc {

class Frame {
public:
  int natom;
  unsigned long nframe;
  int64_t *offsets;
  int step;
  float time;
  matrix box;
  rvec *x;
  float prec;

  // create default constructor
  Frame() { x = (rvec*)malloc(0 * sizeof(rvec)); }
  Frame(int natom) : natom(natom) { x = (rvec*)malloc(natom * sizeof(rvec)); }
  // ~Frame() { free(x); free(offsets); }

  int read_next_frame(XDRFILE *xd)
  {
    int status = read_xtc(xd, natom, &step, &time, box, x, &prec);
    return status;    
  }
};



} // namespace cmdata::xtc

#endif // _XTC_FRAME_HPP