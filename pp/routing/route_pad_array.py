from typing import Any, Callable, List, Tuple, Union

from numpy import float64
from phidl.device_layout import Label

import pp
from pp.component import Component, ComponentReference
from pp.components.electrical.pad import pad as pad_function
from pp.port import select_electrical_ports
from pp.routing.get_route import get_route_electrical
from pp.routing.utils import direction_ports_from_list_ports
from pp.types import Number


def route_pad_array(
    component: Component,
    pad_spacing: float = 150.0,
    pad: Callable = pad_function,
    fanout_length: Number = 20.0,
    max_y0_optical: None = None,
    straight_separation: float = 4.0,
    bend_radius: float = 0.1,
    connected_port_list_ids: None = None,
    n_ports: int = 1,
    excluded_ports: List[Any] = None,
    pad_indices: None = None,
    get_route_function: Callable = get_route_electrical,
    port_name: str = "W",
    pad_rotation: int = -90,
    x_pad_offset: int = 0,
    port_labels: None = None,
    select_ports: Callable = select_electrical_ports,
) -> Tuple[
    List[Union[ComponentReference, Label]], List[List[ComponentReference]], float64
]:
    """Returns component I/O elements north pads and electrical routes.

    Basic routing, typically fine for small components
    No heuristic to avoid collisions between connectors.

    If specified ports to connect in a specific order
    (i.e if connected_port_list_ids is not None and not empty)
    then grab these ports

    Args:
        component: The component to connect.
        pad_spacing: between the pads
        fanout_length: distance between the pads and the southest component port.
            If None, automatically calculated.
        max_y0_optical: Maximum y coordinate for intermediate optical ports
            Usually fine to leave at None.
        straight_separation: min spacing between the straights that route component to pads
        bend_radius: bend radius
        list_port_labels: list of the port indices (e.g [0,3]) which require a TM label.
        connected_port_list_ids: only for type 0 optical routing.
            Can specify which ports goes to which pads
            assuming the gratings are ordered from left to right.
            e.g ['N0', 'W1','W0','E0','E1', 'N1' ] or [4,1,7,3]
        n_ports: number of lines with I/O pads. One line by default.
            WARNING: Only works properly if:
            - n_ports divides the total number of ports
            - the components have an equal number of inputs and outputs
        pad_indices: allows to fine skip some grating slots e.g [0,1,4,5]
            will put two gratings separated by the pitch.
            Then there will be two empty pads slots,
            and after that an additional two gratings.

    Returns:
        elements, pads, y0_optical
    """
    excluded_ports = excluded_ports or []
    if port_labels is None:
        ports = list(select_ports(component.ports).values())
    else:
        ports = [component.ports[lbl] for lbl in port_labels]

    ports = [p for p in ports if p.name not in excluded_ports]
    N = len(ports)
    if N == 0:
        return [], [], 0

    elements = []
    pad = pad() if callable(pad) else pad
    pads = [pad] * N

    io_sep = pad_spacing
    offset = (N - 1) * io_sep / 2.0

    # Get the center along x axis
    x_c = round(sum([p.x for p in ports]) / N, 1)
    y_min = component.ymin  # min([p.y for p in ports])

    # Sort the list of optical ports:
    direction_ports = direction_ports_from_list_ports(ports)
    sep = straight_separation

    K = len(ports)
    K = K + 1 if K % 2 else K

    # Set routing type if not specified

    def has_p(side):
        return len(direction_ports[side]) > 0

    # use x for pad since we rotate it
    y0_optical = y_min - fanout_length - pad.ports[port_name].x
    y0_optical += -K / 2 * sep
    y0_optical = round(y0_optical, 1)

    if max_y0_optical is not None:
        y0_optical = round(min(max_y0_optical, y0_optical), 1)
    """
     - First connect half of the north ports going from middle of list
    down to first elements
     - then connect west ports (top to bottom)
     - then connect south ports (left to right)
     - then east ports (bottom to top)
     - then second half of the north ports (right to left)

    """
    north_ports = direction_ports["N"]
    north_start = north_ports[0 : len(north_ports) // 2]
    north_finish = north_ports[len(north_ports) // 2 :]

    west_ports = direction_ports["W"]
    west_ports.reverse()
    east_ports = direction_ports["E"]
    south_ports = direction_ports["S"]
    north_finish.reverse()  # Sort right to left
    north_start.reverse()  # Sort right to left
    ordered_ports = north_start + west_ports + south_ports + east_ports + north_finish

    nb_ports_per_line = N // n_ports
    pad_size_info = pad.size_info
    y_gap = (K / (n_ports) + 1) * sep
    y_sep = pad_size_info.height + y_gap + bend_radius

    offset = (nb_ports_per_line - 1) * io_sep / 2 - x_pad_offset
    io_pad_lines = []  # [[gr11, gr12, gr13...], [gr21, gr22, gr23...] ...]

    if pad_indices is None:
        pad_indices = list(range(nb_ports_per_line))
    else:
        assert len(pad_indices) == nb_ports_per_line

    for j in range(n_ports):
        pads = [
            pad.ref(
                position=(x_c - offset + i * io_sep, y0_optical - j * y_sep),
                rotation=pad_rotation,
                port_id=port_name,
            )
            for i, pad in zip(pad_indices, pads)
        ]

    io_pad_lines += [pads[:]]

    if connected_port_list_ids:
        ordered_ports = [component.ports[i] for i in connected_port_list_ids]

    for pads in io_pad_lines:
        for i in range(N):
            p0 = pads[i].ports[port_name]
            p1 = ordered_ports[i]
            route = get_route_function(p1, p0)
            elements.extend(route["references"])

    return elements, io_pad_lines, y0_optical


if __name__ == "__main__":

    c = pp.components.wg_heater_connected()
    c = pp.components.mzi2x2(with_elec_connections=True)

    elements, pads, _ = route_pad_array(c, fanout_length=100)
    for e in elements:
        c.add(e)
    for e in pads:
        c.add(e)
    c.show()
